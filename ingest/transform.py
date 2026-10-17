"""Convert cached GitHub responses to the exact graph writer record shapes."""
import base64
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from ingest.github_loader import REPO

DATA = Path(__file__).parent / 'data'
URL = 'https://github.com/' + REPO


class Records:
    def __init__(self):
        self.nodes = defaultdict(dict)
        self.edges = defaultdict(dict)

    def node(self, label, id, name, source_url, synthetic=False, **props):
        self.nodes[label][id] = dict(id=id, name=name, source_url=source_url,
                                    synthetic=synthetic, **props)
        return id

    def edge(self, kind, a_label, a, b_label, b, source_url, synthetic=False, **props):
        self.edges[kind, a_label, b_label][a, b] = dict(
            from_id=a, to_id=b, source_url=source_url, synthetic=synthetic, **props)

    def person(self, user):
        if not user or not user.get('login'):
            return None
        login = user['login']
        return self.node('Person', 'person:' + login, login,
                         user.get('html_url') or 'https://github.com/' + login,
                         github_login=login)

    def counts(self):
        edges = defaultdict(int)
        for (kind, _, _), rows in self.edges.items():
            edges[kind] += len(rows)
        return dict(nodes_by_label={k: len(v) for k, v in self.nodes.items()},
                    edges_by_type=dict(edges))


def decode(record):
    return base64.b64decode(record['blob']['content']).decode('utf-8', errors='replace')


def architecture(out):
    data = json.loads((DATA / 'services.json').read_text())
    for s in data['services']:
        source = URL + '/tree/main/src/' + s['name']
        if s['name'] == 'redis-cart':
            source = URL + '/blob/main/kubernetes-manifests/redis.yaml'
        out.node('Service', 'svc:' + s['name'], source_url=source, **s)
    for caller, callees in data['dependencies'].items():
        for callee in callees:
            out.edge('DEPENDS_ON', 'Service', 'svc:' + caller, 'Service', 'svc:' + callee,
                     data['source_url'], weight=1.0)
    return data


def real(snapshot):
    out = Records()
    architecture(out)
    repo = snapshot['repo']
    branch = repo['default_branch']
    repo_id = out.node('Repo', 'repo:' + REPO, REPO, URL, default_branch=branch)

    def file(path):
        id = out.node('File', 'file:' + path, Path(path).name,
                      URL + '/blob/' + quote(branch, safe='') + '/' + quote(path), path=path)
        out.edge('CONTAINS', 'Repo', repo_id, 'File', id, URL)
        parts = path.split('/')
        if len(parts) > 2 and parts[0] == 'src' and 'svc:' + parts[1] in out.nodes['Service']:
            out.edge('CONTAINS', 'Service', 'svc:' + parts[1], 'File', id,
                     out.nodes['File'][id]['source_url'])
        return id

    for user in snapshot.get('contributors', []):
        out.person(user)
    for label, key in [('PR', 'pulls'), ('Commit', 'commits')]:
        for record in snapshot.get(key, []):
            d = record['detail']
            if label == 'PR':
                id = out.node(label, 'pr:' + str(d['number']), d['title'], d['html_url'],
                              number=d['number'], merged_at=d.get('merged_at'),
                              body=(d.get('body') or '')[:60000])
                user = d.get('user')
            else:
                message = d['commit']['message']
                id = out.node(label, 'commit:' + d['sha'], message.splitlines()[0],
                              d['html_url'], sha=d['sha'], message=message[:60000],
                              authored_at=d['commit']['author']['date'])
                user = d.get('author')
            person = out.person(user)
            if person:
                out.edge('AUTHORED', 'Person', person, label, id, d['html_url'])
            for changed in record['files']:
                out.edge('TOUCHED', label, id, 'File', file(changed['filename']), d['html_url'],
                         additions=changed.get('additions', 0), deletions=changed.get('deletions', 0))
    for record in snapshot.get('issues', []):
        d = record['detail']
        id = out.node('Issue', 'issue:' + str(d['number']), d['title'], d['html_url'],
                      number=d['number'], state=d['state'], body=(d.get('body') or '')[:60000],
                      labels=[x['name'] for x in d.get('labels', [])])
        person = out.person(d.get('user'))
        if person:
            out.edge('AUTHORED', 'Person', person, 'Issue', id, d['html_url'])
        mentions(out, 'Issue', id, d['title'] + '\n' + (d.get('body') or ''), d['html_url'])
        for link in record.get('linked_pulls', []):
            if link['repository']['nameWithOwner'] != REPO:
                continue
            pid = 'pr:' + str(link['number'])
            if pid in out.nodes['PR']:
                out.edge('RESOLVED_BY', 'Issue', id, 'PR', pid, d['html_url'])
    for record in snapshot.get('docs', []):
        body = decode(record)
        path = record['path']
        file(path)
        heading = next((line.lstrip('# ').strip() for line in body.splitlines()
                        if line.startswith('# ')), Path(path).name)
        url = URL + '/blob/' + quote(branch, safe='') + '/' + quote(path)
        id = out.node('Doc', 'doc:' + path, heading, url, kind='readme', body=body[:60000])
        mentions(out, 'Doc', id, body, url)
    codeowners(out, snapshot.get('codeowners', []), file)
    return out


def mentions(out, label, id, text, url):
    for sid, service in out.nodes['Service'].items():
        if re.search(r'(?<![\w])' + re.escape(service['name']) + r'(?![\w])', text, re.I):
            out.edge('MENTIONS', label, id, 'Service', sid, url)


def codeowners(out, records, add_file):
    import fnmatch

    for record in records[:1]:  # Collector orders paths; prefer .github/CODEOWNERS.
        source = URL + '/blob/main/' + record['path']
        add_file(record['path'])
        rules = []
        for line in decode(record).splitlines():
            tokens = line.split('#', 1)[0].split()
            if tokens and not tokens[0].startswith(('!', '[')):
                rules.append((tokens[0], tokens[1:]))
        for fid, f in list(out.nodes['File'].items()):
            selected = None
            for pattern, owners in rules:
                glob = pattern.lstrip('/')
                if glob.endswith('/'):
                    glob += '**'
                if fnmatch.fnmatchcase(f['path'], glob) or (
                    '/' not in glob and any(fnmatch.fnmatchcase(p, glob)
                                           for p in f['path'].split('/'))
                ):
                    selected = pattern, owners
            if selected is None:
                continue
            pattern, owners = selected
            for owner in owners:
                handle = owner.lstrip('@')
                if owner.startswith('@') and '/' in handle:
                    org, slug = handle.split('/', 1)
                    label = 'Team'
                    oid = out.node(label, 'team:gh:' + handle, handle,
                                   f'https://github.com/orgs/{org}/teams/{slug}',
                                   team_kind='github', github_handle=owner)
                else:
                    label = 'Person'
                    if owner.startswith('@'):
                        oid = out.person({'login': handle})
                    else:
                        oid = out.node(label, 'person:email:' + owner, owner, source)
                out.edge('OWNS', label, oid, 'File', fid, source, pattern=pattern)

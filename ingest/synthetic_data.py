"""Deterministic demo narratives; no invented memberships for real people."""
import json
from datetime import datetime, timedelta

from ingest.transform import DATA


def populate(out, now=None):
    spec = json.loads((DATA / 'synthetic_layer.json').read_text())
    now = now or datetime.fromisoformat(spec['as_of'].replace('Z', '+00:00'))
    stamp = lambda d: d.isoformat(timespec='seconds').replace('+00:00', 'Z')
    dependencies = json.loads((DATA / 'services.json').read_text())['dependencies']
    touched = {}
    for (kind, a, b), records in out.edges.items():
        if (kind, a, b) == ('TOUCHED', 'PR', 'File'):
            for r in records.values():
                path = r['to_id'].removeprefix('file:').split('/')
                if len(path) > 2 and path[0] == 'src':
                    touched.setdefault(path[1], set()).add(r['from_id'])
    def artifacts(service):
        return sorted(touched.get(service, []), key=lambda p: out.nodes['PR'][p]['number'])

    for team in spec['teams']:
        tid = out.node('Team', 'team:' + team['slug'], team['name'], 'synthetic', True,
                       team_kind='oncall', pager_channel=team['pager_channel'])
        for i in range(2):
            pid = out.node('Person', 'person:demo-' + team['slug'] + '-' + str(i + 1),
                           team['name'] + ' engineer ' + str(i + 1), 'synthetic', True,
                           role='Synthetic on-call engineer')
            out.edge('MEMBER_OF', 'Person', pid, 'Team', tid, 'synthetic', True,
                     since='2025-10-01T00:00:00Z')
        for service in team['services']:
            out.edge('OWNS', 'Team', tid, 'Service', 'svc:' + service,
                     'synthetic', True, role='primary')
    for d in spec['decisions']:
        did = out.node('Decision', 'decision:' + d['slug'], d['name'], 'synthetic', True,
                       status='accepted', context='FABRICATED DEMO ADR. ' + d['context'] +
                       ' Linked real artifacts do not establish any historical claim.',
                       decided_at='2025-10-01T00:00:00Z')
        out.edge('DECIDED', 'Decision', did, 'Service', 'svc:' + d['service'], 'synthetic', True)
        prs = artifacts(d['service'])
        if prs:
            out.edge('CITES', 'Decision', did, 'PR', prs[0], 'synthetic', True)
        doc = 'doc:src/' + d['service'] + '/README.md'
        if doc not in out.nodes['Doc']:
            doc = 'doc:README.md'
        if doc in out.nodes['Doc']:
            out.edge('CITES', 'Decision', did, 'Doc', doc, 'synthetic', True)
    missing = []
    for i, inc in enumerate(spec['incidents']):
        started = now - timedelta(days=inc['days_ago'])
        iid = out.node('Incident', 'incident:' + inc['slug'], inc['name'], 'synthetic', True,
                       severity=inc['severity'], started_at=stamp(started),
                       resolved_at=stamp(started + timedelta(minutes=inc['duration_minutes'])),
                       summary='FABRICATED DEMO INCIDENT. ' + inc['summary'] +
                       ' Real PRs are illustrative artifacts only; no claim about their authors'
                       ' or actual production failures is intended.')
        service = inc['service']
        out.edge('CAUSED', 'Incident', iid, 'Service', 'svc:' + service, 'synthetic', True)
        affected = {service}
        while True:
            more = {caller for caller, callees in dependencies.items()
                    if affected.intersection(callees)}
            if more <= affected:
                break
            affected |= more
        for target in sorted(affected):
            out.edge('AFFECTED', 'Incident', iid, 'Service', 'svc:' + target, 'synthetic', True)
        prs = artifacts(service)
        merged = [p for p in prs if out.nodes['PR'][p].get('merged_at')]
        if prs:
            out.edge('CAUSED', 'Incident', iid, 'PR', prs[i % len(prs)], 'synthetic', True)
        if merged:
            fix = next((p for p in reversed(merged) if not prs or p != prs[i % len(prs)]),
                       merged[-1])
            out.edge('RESOLVED_BY', 'Incident', iid, 'PR', fix, 'synthetic', True)
        if not prs or not merged:
            missing.append({'incident': iid, 'service': service, 'cause_available': bool(prs),
                            'merged_resolution_available': bool(merged)})
        for d in spec['decisions']:
            if d['service'] == service:
                out.edge('CITES', 'Incident', iid, 'Decision', 'decision:' + d['slug'],
                         'synthetic', True)
    return missing

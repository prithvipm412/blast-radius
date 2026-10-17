"""Read-only GitHub collection with restartable, raw JSON response caching.

No graph representation is inferred here. In particular commits, issue timeline
links and CODEOWNERS remain raw until their schema is agreed with the lead.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

import httpx

LOG = logging.getLogger(__name__)
REPO = "GoogleCloudPlatform/microservices-demo"
CACHE = Path(__file__).parent / "cache"


class GitHub:
    def __init__(self, cache: Path = CACHE, client=None, sleep=time.sleep):
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.sleep = sleep
        self.requests = 0
        self.cache_hits = 0
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
        self.client = client or httpx.Client(
            base_url="https://api.github.com", headers=headers, timeout=60
        )

    def close(self):
        self.client.close()

    def get(self, path: str, params=None, *, refresh=False, payload=None):
        key = json.dumps([path, params or {}] if payload is None else
                         [path, params or {}, payload], sort_keys=True)
        filename = self.cache / (hashlib.sha256(key.encode()).hexdigest() + ".json")
        if filename.exists() and not refresh:
            self.cache_hits += 1
            return json.loads(filename.read_text())["response"]
        for attempt in range(6):
            self.requests += 1
            try:
                response = (self.client.get(path, params=params) if payload is None else
                            self.client.post(path, json=payload))
            except httpx.TransportError:
                if attempt == 5:
                    raise
                self.sleep(2 ** attempt)
                continue
            limited = response.status_code == 429 or (
                response.status_code == 403 and (
                    response.headers.get("x-ratelimit-remaining") == "0"
                    or "retry-after" in response.headers
                    or "rate limit" in response.text.lower()
                )
            )
            if limited or response.status_code >= 500:
                if attempt == 5:
                    response.raise_for_status()
                delay = float(response.headers.get("retry-after", 2 ** attempt))
                if response.headers.get("x-ratelimit-remaining") == "0":
                    delay = max(delay, float(response.headers.get(
                        "x-ratelimit-reset", time.time() + 60)) - time.time() + 1)
                LOG.warning("GitHub throttled/unavailable; retrying in %.0fs", delay)
                self.sleep(max(1, delay))
                continue
            response.raise_for_status()
            data = response.json()
            if payload is not None and data.get('errors'):
                raise RuntimeError('GitHub GraphQL error: ' + json.dumps(data['errors']))
            temporary = filename.with_suffix(".tmp")
            temporary.write_text(json.dumps({"path": path, "params": params or {},
                                             "response": data}, ensure_ascii=False))
            temporary.replace(filename)
            return data
        raise RuntimeError("GitHub retry budget exhausted")

    def pages(self, path, params=None, *, limit=None, refresh=False):
        result = []
        page = 1
        while limit is None or len(result) < limit:
            batch = self.get(path, {**(params or {}), "per_page": 100, "page": page},
                             refresh=refresh)
            if not isinstance(batch, list):
                raise ValueError("Expected GitHub paginated list: " + path)
            result.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return result if limit is None else result[:limit]

    def pull(self, number, *, refresh=False):
        path = f"/repos/{REPO}/pulls/{number}"
        return {"detail": self.get(path, refresh=refresh),
                "files": self.pages(path + "/files", refresh=refresh)}

    def issue(self, issue, *, refresh=False):
        return {"detail": issue, "timeline": self.pages(
            f"/repos/{REPO}/issues/{issue['number']}/timeline", refresh=refresh)}

    def linked_pulls(self, issue_number, *, refresh=False):
        # GitHub's explicit closing references, not arbitrary timeline cross-references.
        # https://docs.github.com/en/graphql/reference/issues
        query = '''query($owner:String!, $repo:String!, $number:Int!, $after:String) {
          repository(owner:$owner, name:$repo) { issue(number:$number) {
            closedByPullRequestsReferences(first:100, after:$after, includeClosedPrs:true) {
              nodes { number url repository { nameWithOwner } }
              pageInfo { hasNextPage endCursor }
            }
          } }
        }'''
        owner, repo = REPO.split('/')
        after, result = None, []
        while True:
            response = self.get('/graphql', refresh=refresh, payload={
                'query': query, 'variables': dict(owner=owner, repo=repo,
                                                 number=issue_number, after=after)})
            connection = response['data']['repository']['issue']['closedByPullRequestsReferences']
            result.extend(connection['nodes'])
            if not connection['pageInfo']['hasNextPage']:
                return result
            after = connection['pageInfo']['endCursor']

    def enrich_links(self, snapshot, *, refresh=False):
        pulls = {r['detail']['number']: r for r in snapshot['pulls']}
        for record in snapshot['issues']:
            links = self.linked_pulls(record['detail']['number'], refresh=refresh)
            record['linked_pulls'] = links
            for link in links:
                if link['repository']['nameWithOwner'] == REPO and link['number'] not in pulls:
                    pulls[link['number']] = self.pull(link['number'], refresh=refresh)
        snapshot['pulls'] = list(pulls.values())
        return snapshot

    def collect(self, commit_limit=300, pr_limit=200, issue_limit=200):
        root = f"/repos/{REPO}"
        repo = self.get(root)
        contributors = self.pages(root + "/contributors")
        commits = []
        for item in self.pages(root + "/commits", limit=commit_limit):
            path = root + "/commits/" + item["sha"]
            detail = self.get(path, {"per_page": 100, "page": 1})
            files = list(detail.get("files", []))
            page = 2
            while len(files) and len(files) % 100 == 0:
                batch = self.get(path, {"per_page": 100, "page": page})["files"]
                files.extend(batch)
                if len(batch) < 100:
                    break
                page += 1
            commits.append({"detail": detail, "files": files})
        pulls = []
        for item in self.pages(
            root + "/pulls", {"state": "all", "sort": "updated", "direction": "desc"},
            limit=pr_limit):
            try:
                pulls.append(self.pull(item['number']))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                LOG.warning('PR %s disappeared after listing; skipping', item['number'])
        issues = []
        page = 1
        while len(issues) < issue_limit:
            batch = self.get(root + "/issues", {"state": "all", "per_page": 100,
                                                   "page": page})
            if not batch:
                break
            for item in batch:
                if "pull_request" not in item and len(issues) < issue_limit:
                    issues.append(self.issue(item))
            page += 1
        tree = self.get(root + "/git/trees/" + repo["default_branch"], {"recursive": 1})
        if tree.get("truncated"):
            raise ValueError("Repository tree truncated; refusing an incomplete documentation load")
        docs, codeowners = [], []
        for entry in tree["tree"]:
            path = entry["path"]
            if entry["type"] != "blob":
                continue
            if path.lower().endswith(".md") or path in (
                ".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"
            ):
                record = {"path": path, "blob": self.get(root + "/git/blobs/" + entry["sha"])}
                (docs if path.lower().endswith(".md") else codeowners).append(record)
        return self.enrich_links({"repo": repo, "contributors": contributors, "commits": commits,
                "pulls": pulls, "issues": issues, "docs": docs, "codeowners": codeowners})

    def updated(self, since: str):
        """Issues endpoint includes changed PRs and supports a server-side watermark."""
        items = self.pages(f"/repos/{REPO}/issues", {
            "state": "all", "since": since, "sort": "updated", "direction": "asc"
        }, refresh=True)
        return self.enrich_links({
            "pulls": [self.pull(i["number"], refresh=True) for i in items if "pull_request" in i],
            "issues": [self.issue(i, refresh=True) for i in items if "pull_request" not in i],
        }, refresh=True)


def main():
    """Collect a raw snapshot without changing the graph."""
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    client = GitHub()
    try:
        snapshot = client.collect()
        target = CACHE / "snapshot.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False))
        temporary.replace(target)
        print(json.dumps({key: len(value) for key, value in snapshot.items()
                          if isinstance(value, list)}, indent=2))
        print(f"Requests: {client.requests}; cache hits: {client.cache_hits}")
    finally:
        client.close()


if __name__ == "__main__":
    main()

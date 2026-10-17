import json

import httpx
import pytest

from ingest.github_loader import GitHub


def make_client(tmp_path, handler, sleep=lambda _: None):
    return GitHub(tmp_path, httpx.Client(base_url="https://api.github.com",
                                        transport=httpx.MockTransport(handler)), sleep)


def test_cache_and_refresh(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"version": len(calls)})

    client = make_client(tmp_path, handler)
    assert client.get("/repo") == {"version": 1}
    assert client.get("/repo") == {"version": 1}
    assert client.get("/repo", refresh=True) == {"version": 2}
    assert client.cache_hits == 1
    assert len(calls) == 2
    assert json.loads(next(tmp_path.glob("*.json")).read_text())["response"] == {"version": 2}


def test_pagination_and_limit(tmp_path):
    client = make_client(tmp_path, lambda r: httpx.Response(
        200, json=list(range(100)) if r.url.params["page"] == "1" else [100, 101]))
    assert len(client.pages("/items")) == 102
    assert len(client.pages("/items", limit=101)) == 101


def test_rate_limit_retries(tmp_path):
    waits, calls = [], []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "3"})
        return httpx.Response(200, json=[])

    client = make_client(tmp_path, handler, waits.append)
    assert client.get("/items") == []
    assert waits == [3]


def test_permission_error_not_cached_or_retried(tmp_path):
    client = make_client(tmp_path, lambda _: httpx.Response(403, json={"message": "Forbidden"}))
    with pytest.raises(httpx.HTTPStatusError):
        client.get("/private")
    assert client.requests == 1
    assert not list(tmp_path.iterdir())


def test_incremental_refreshes_details_and_files(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        path = request.url.path
        if path == '/graphql':
            return httpx.Response(200, json={'data': {'repository': {'issue': {
                'closedByPullRequestsReferences': {'nodes': [], 'pageInfo': {'hasNextPage': False}}
            }}}})
        if path.endswith("/issues"):
            return httpx.Response(200, json=[{"number": 1, "pull_request": {}}, {"number": 2}])
        if path.endswith("/pulls/1"):
            return httpx.Response(200, json={"number": 1})
        return httpx.Response(200, json=[])

    client = make_client(tmp_path, handler)
    for _ in range(2):
        result = client.updated("2026-01-01T00:00:00Z")
        assert len(result["pulls"]) == len(result["issues"]) == 1
    assert len(requests) == 10
    assert requests[0].url.params["since"] == "2026-01-01T00:00:00Z"


def test_explicit_links_fetch_missing_prs_and_ignore_external_repos(tmp_path):
    def handler(request):
        if request.url.path == '/graphql':
            return httpx.Response(200, json={'data': {'repository': {'issue': {
                'closedByPullRequestsReferences': {
                    'nodes': [
                        {'number': 99, 'repository': {'nameWithOwner': 'GoogleCloudPlatform/microservices-demo'}},
                        {'number': 50, 'repository': {'nameWithOwner': 'other/repo'}}],
                    'pageInfo': {'hasNextPage': False}}
            }}}})
        if request.url.path.endswith('/pulls/99'):
            return httpx.Response(200, json={'number': 99})
        return httpx.Response(200, json=[])
    client = make_client(tmp_path, handler)
    result = client.enrich_links({'pulls': [], 'issues': [{'detail': {'number': 1}}]})
    assert [p['detail']['number'] for p in result['pulls']] == [99]
    assert len(result['issues'][0]['linked_pulls']) == 2


def test_transport_error_retries(tmp_path):
    attempts = []
    def handler(request):
        attempts.append(request)
        if len(attempts) == 1:
            raise httpx.ConnectError('transient')
        return httpx.Response(200, json={'ok': True})
    client = make_client(tmp_path, handler)
    assert client.get('/repo') == {'ok': True}
    assert len(attempts) == 2

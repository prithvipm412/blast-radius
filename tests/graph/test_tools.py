import json
from datetime import UTC, datetime

import pytest

from graph import tools


def check(result):
    assert set(result) == {"data", "cypher", "params", "path"}
    json.dumps(result)
    nodes = result["path"]["nodes"]
    ids = {n["id"] for n in nodes}
    assert len(ids) == len(nodes)
    for e in result["path"]["edges"]:
        assert e["source"] in ids and e["target"] in ids
        assert isinstance(e["synthetic"], bool)
    return result["data"]


def test_search(graph):
    assert check(tools.search_entities("CARTSERVICE"))["matches"]
    assert check(tools.search_entities("' OR 1=1 //"))["matches"] == []


def test_blast(graph):
    result = tools.blast_radius("cartservice")
    assert {n["id"]: n["depth"] for n in check(result)["affected"]} == {
        "svc:frontend": 1,
        "svc:checkoutservice": 1,
    }
    assert {e["target"] for e in result["path"]["edges"]} == {"svc:cartservice"}
    assert check(tools.blast_radius("cartservice", 0))["affected"] == []
    assert check(tools.blast_radius("frontend"))["affected"] == []


def test_experts(graph):
    result = tools.find_experts("cartservice", days=10000)
    assert check(result)["experts"] == [
        {
            "id": "person:alice",
            "name": "Alice Nguyen",
            "pr_count": 1,
            "last_touched": "2024-05-01T12:00:00Z",
        }
    ]
    assert "pr:234" in {n["id"] for n in result["path"]["nodes"]}
    # days=0 finds nobody in-window, but <3 humans triggers the all-time widen fallback,
    # so alice still turns up rather than a misleadingly empty result.
    assert check(tools.find_experts("cartservice", days=0))["experts"] == [
        {"id": "person:alice", "name": "Alice Nguyen", "pr_count": 1, "last_touched": "2024-05-01T12:00:00Z"}
    ]


def test_experts_bot_filter_and_widen(graph):
    # A bot-authored PR, merged "now" (always in-window) - must never count as an expert
    # nor appear in evidence, and must not count toward the <3-humans widen threshold.
    graph.query(
        "CREATE (p:Person {id:'person:renovate-bot', name:'renovate-bot', synthetic:false, "
        "source_url:'https://github.com/renovate-bot', github_login:'renovate-bot'})",
        {},
    )
    now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    graph.query(
        "CREATE (pr:PR {id:'pr:999', name:'Bump dep', source_url:'https://example/pr/999', "
        "synthetic:false, number:999, merged_at:$now, body:''}) "
        "WITH pr MATCH (f:File {id:'file:src/cartservice/src/CartService.cs'}) "
        "CREATE (pr)-[:TOUCHED {synthetic:false, additions:1, deletions:1}]->(f) "
        "WITH pr MATCH (p:Person {id:'person:renovate-bot'}) "
        "CREATE (p)-[:AUTHORED {synthetic:false}]->(pr)",
        {"now": now},
    )
    try:
        # Narrow window: only the bot PR is "recent"; alice's 2024 PR is out of range. The
        # bot doesn't satisfy the human quota, so this must widen to all-time and surface
        # alice - not report the bot, and not report an empty list.
        result = tools.find_experts("cartservice", days=1)
        data = check(result)
        assert data["experts"] == [
            {"id": "person:alice", "name": "Alice Nguyen", "pr_count": 1,
             "last_touched": "2024-05-01T12:00:00Z"}
        ]
        path_ids = {n["id"] for n in result["path"]["nodes"]}
        assert "person:renovate-bot" not in path_ids
        assert "pr:999" not in path_ids
    finally:
        graph.query(
            "MATCH (n) WHERE n.id IN $ids DETACH DELETE n",
            {"ids": ["person:renovate-bot", "pr:999"]},
        )


def test_incidents(graph):
    result = tools.similar_incidents("cartservice")
    assert check(result)["incidents"][0]["relation"] == "CAUSED"
    assert len(result["data"]["incidents"]) == 1
    assert (
        check(tools.similar_incidents("paymentservice"))["incidents"][0]["relation"] == "AFFECTED"
    )


def test_similar_incidents_ranked_and_capped(graph):
    same_service = [("incident:same-0", "2020-01-01T00:00:00Z"),
                     ("incident:same-1", "2020-02-01T00:00:00Z"),
                     ("incident:same-2", "2020-03-01T00:00:00Z")]
    downstream = [("incident:down-0", "2021-01-01T00:00:00Z"),
                  ("incident:down-1", "2021-02-01T00:00:00Z"),
                  ("incident:down-2", "2021-03-01T00:00:00Z")]
    for id_, started in same_service:
        graph.query(
            "CREATE (i:Incident {id:$id, name:$id, synthetic:true, source_url:'synthetic', "
            "severity:'sev3', started_at:$started}) "
            "WITH i MATCH (s:Service {id:'svc:cartservice'}) "
            "CREATE (i)-[:CAUSED {synthetic:true}]->(s)",
            {"id": id_, "started": started},
        )
    for id_, started in downstream:
        graph.query(
            "CREATE (i:Incident {id:$id, name:$id, synthetic:true, source_url:'synthetic', "
            "severity:'sev3', started_at:$started}) "
            "WITH i MATCH (s:Service {id:'svc:frontend'}) "
            "CREATE (i)-[:AFFECTED {synthetic:true}]->(s)",
            {"id": id_, "started": started},
        )
    all_ids = [id_ for id_, _ in same_service + downstream]
    try:
        result = tools.similar_incidents("cartservice")
        data = check(result)
        # inc-003 (fixture, CAUSED, 2024) outranks all 3 injected same-service incidents by
        # recency; same-service always outranks downstream, so exactly 1 of the 3 downstream
        # incidents (the most recent) fills the last of 5 slots.
        assert [i["id"] for i in data["incidents"]] == [
            "incident:inc-003", "incident:same-2", "incident:same-1",
            "incident:same-0", "incident:down-2",
        ]
        kept_ids = {i["id"] for i in data["incidents"]}
        path_incident_ids = {n["id"] for n in result["path"]["nodes"] if n["label"] == "Incident"}
        assert path_incident_ids == kept_ids
    finally:
        graph.query("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", {"ids": all_ids})


def test_decisions(graph):
    result = tools.trace_decision("cartservice")
    assert check(result)["decisions"][0]["id"] == "decision:use-grpc"
    assert "incident:inc-003" in {n["id"] for n in result["path"]["nodes"]}


@pytest.mark.parametrize(
    "fn", [tools.blast_radius, tools.find_experts, tools.similar_incidents, tools.trace_decision]
)
def test_unknown(graph, fn):
    with pytest.raises(ValueError, match="unknown service: no-such-service"):
        fn("no-such-service")


@pytest.mark.parametrize("fn", [tools.critical_services, tools.single_points_of_failure])
def test_rankings(graph, fn):
    result = fn()
    ranked = check(result)["ranked"]
    assert len(ranked) == 5
    assert [r["score"] for r in ranked] == sorted((r["score"] for r in ranked), reverse=True)
    assert len(result["path"]["edges"]) == 5


def test_clusters(graph):
    result = tools.team_clusters()
    clusters = check(result)["clusters"]
    assert sum(len(c["services"]) for c in clusters) == 5
    assert any(c["dominant_team"] == "team:payments" for c in clusters)
    assert len(result["path"]["edges"]) == 7


@pytest.mark.parametrize(
    "fn", [tools.critical_services, tools.single_points_of_failure, tools.team_clusters]
)
def test_fallback(graph, monkeypatch, fn):
    from graph import algorithms

    monkeypatch.setattr(algorithms, "_procedures", lambda graph: frozenset())
    result = fn()
    assert check(result)["method"] == "networkx-fallback"
    assert len(result["path"]["nodes"]) >= 5


def test_owners(graph):
    result = tools.find_owners("cartservice")
    assert check(result)["team"]["id"] == "team:payments"
    assert {m["id"] for m in result["data"]["members"]} == {"person:alice", "person:bob"}
    assert len(result["data"]["teams"]) == 1
    assert len(result["path"]["edges"]) == 3
    assert check(tools.find_owners("frontend")) == {"team": None, "members": [], "teams": []}


def test_owners_multiple_teams(graph):
    graph.query(
        "CREATE (t:Team {id:$id, name:$name, synthetic:true, source_url:'synthetic'}) "
        "WITH t MATCH (s:Service {id:'svc:cartservice'}) CREATE (t)-[:OWNS {synthetic:true}]->(s)",
        {"id": "team:sre", "name": "SRE"},
    )
    graph.query(
        "CREATE (p:Person {id:$id, name:$name, synthetic:true, source_url:'synthetic'}) "
        "WITH p MATCH (t:Team {id:'team:sre'}) CREATE (p)-[:MEMBER_OF {synthetic:true}]->(t)",
        {"id": "person:carol", "name": "Carol"},
    )
    try:
        result = tools.find_owners("cartservice")
        data = check(result)
        assert {t["id"] for t in data["teams"]} == {"team:payments", "team:sre"}
        sre = next(t for t in data["teams"] if t["id"] == "team:sre")
        assert {m["id"] for m in sre["members"]} == {"person:carol"}
        # Backward-compatible single-team fields still resolve deterministically (lowest id).
        assert data["team"]["id"] == "team:payments"
    finally:
        graph.query(
            "MATCH (n) WHERE n.id IN $ids DETACH DELETE n",
            {"ids": ["team:sre", "person:carol"]},
        )


def test_failure_path(graph):
    result = tools.failure_path("cartservice", "frontend")
    assert check(result) == {
        "exists": True,
        "hops": 1,
        "path_ids": ["svc:cartservice", "svc:frontend"],
    }
    assert result["path"]["edges"][0]["source"] == "svc:frontend"
    assert "direction" not in result["data"]
    assert check(tools.failure_path("cartservice", "cartservice"))["hops"] == 0
    with pytest.raises(ValueError, match="unknown service"):
        tools.failure_path("bogus", "cartservice")


def test_failure_path_undirected_fallback(graph):
    # paymentservice and productcatalogservice share a dependent (checkoutservice) but
    # neither depends on the other, so no directed incoming-chain exists either way.
    result = tools.failure_path("paymentservice", "productcatalogservice")
    data = check(result)
    assert data == {
        "exists": True,
        "hops": 2,
        "path_ids": ["svc:paymentservice", "svc:checkoutservice", "svc:productcatalogservice"],
        "direction": "undirected",
    }
    assert len(result["path"]["edges"]) == 2


def test_draft(graph, monkeypatch):
    from graph import issues

    monkeypatch.setattr(
        issues, "_post_issue", lambda *args: pytest.fail("dry run contacted GitHub")
    )
    result = tools.create_incident_issue("cartservice", "Test outage ' $param //")
    data = check(result)
    assert data["dry_run"] and data["url"] == "draft"
    for section in ("Blast radius", "Owners", "Experts", "Similar incidents", "Decision context"):
        assert "## " + section in data["body"]
    assert "https://github.com/" in data["body"]
    assert "synthetic; no external source" in data["body"]
    row = graph.query(
        "MATCH (i:Incident {id:$id})-[e:CAUSED]->(s) RETURN i, e, s", {"id": data["incident_id"]}
    ).result_set[0]
    assert row[0].properties["synthetic"] is True
    assert row[1].properties["synthetic"] is True
    graph.query(
        "MATCH (n) WHERE n.id IN $ids DETACH DELETE n",
        {"ids": [data["incident_id"], data["issue_id"]]},
    )


def test_filing_guards(graph, monkeypatch):
    monkeypatch.delenv("GITHUB_ISSUE_REPO", raising=False)
    with pytest.raises(ValueError, match="GITHUB_ISSUE_REPO"):
        tools.create_incident_issue("cartservice", "outage", False)
    monkeypatch.setenv("GITHUB_ISSUE_REPO", "GoogleCloudPlatform/microservices-demo")
    with pytest.raises(ValueError, match="upstream"):
        tools.create_incident_issue("cartservice", "outage", False)


def test_filing_mocked(graph, monkeypatch):
    from graph import issues

    monkeypatch.setenv("GITHUB_ISSUE_REPO", "demo-owner/incident-test")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    calls = []

    def post(repo, token, title, body):
        calls.append(repo)
        return 987654, "https://github.com/demo-owner/incident-test/issues/987654"

    monkeypatch.setattr(issues, "_post_issue", post)
    result = tools.create_incident_issue("cartservice", "outage", False)
    assert check(result)["issue_id"] == "issue:987654"
    assert calls == ["demo-owner/incident-test"]
    graph.query(
        "MATCH (n) WHERE n.id IN $ids DETACH DELETE n",
        {"ids": [result["data"]["incident_id"], result["data"]["issue_id"]]},
    )


def test_schema_idempotent(graph):
    from graph.schema import ensure_schema

    ensure_schema(graph)
    ensure_schema(graph)
    assert len(graph.list_constraints()) == 12


def test_mcp_schema():
    import asyncio
    import inspect

    from graph.mcp_server import TOOL_NAMES, mcp

    registered = asyncio.run(mcp.list_tools())
    assert {t.name for t in registered} == set(TOOL_NAMES)
    for tool in registered:
        signature = inspect.signature(getattr(tools, tool.name))
        assert set(tool.inputSchema["properties"]) == set(signature.parameters)
        for name, param in signature.parameters.items():
            if param.default is not inspect.Parameter.empty:
                assert tool.inputSchema["properties"][name]["default"] == param.default


def test_multihop_cycle_and_distinct_prs(graph):
    graph.query(
        "MATCH (a:Service {id:$a}), (b:Service {id:$b}) "
        "CREATE (a)-[:DEPENDS_ON {synthetic:false}]->(b)",
        {"a": "svc:cartservice", "b": "svc:paymentservice"},
    )
    try:
        result = tools.blast_radius("paymentservice", 2)
        affected = {n["id"]: n["depth"] for n in result["data"]["affected"]}
        assert affected == {"svc:cartservice": 1, "svc:checkoutservice": 1, "svc:frontend": 2}
        assert "svc:frontend" not in {
            n["id"] for n in tools.blast_radius("paymentservice", 1)["data"]["affected"]
        }
        path = tools.failure_path("paymentservice", "frontend")
        assert path["data"]["path_ids"] == ["svc:paymentservice", "svc:cartservice", "svc:frontend"]
    finally:
        graph.query(
            "MATCH (a {id:$a})-[e:DEPENDS_ON]->(b {id:$b}) DELETE e",
            {"a": "svc:cartservice", "b": "svc:paymentservice"},
        )


def test_errors_are_not_fallback(monkeypatch):
    from graph import algorithms

    monkeypatch.setattr(algorithms, "get_graph", lambda: object())
    monkeypatch.setattr(algorithms, "_procedures", lambda graph: {"algo.pageRank"})

    def broken(*args):
        raise RuntimeError("query failed")

    with pytest.raises(RuntimeError, match="query failed"):
        algorithms.run_algorithm("pagerank", broken, tools._result, tools.CAP)


def test_mcp_stdio(graph):
    import asyncio
    import os
    import sys

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "graph.mcp_server"],
            env={**os.environ, "FALKORDB_GRAPH": "blast_radius_test"},
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            registered = await session.list_tools()
            assert len(registered.tools) == 11
            result = await session.call_tool("blast_radius", {"service": "cartservice"})
            assert not result.isError
            assert check(result.structuredContent)["root"] == "svc:cartservice"

    asyncio.run(exercise())


def test_warm_latency(graph):
    from statistics import median
    from time import perf_counter

    calls = {
        "search_entities": lambda: tools.search_entities("cart"),
        "blast_radius": lambda: tools.blast_radius("cartservice"),
        "failure_path": lambda: tools.failure_path("cartservice", "frontend"),
        "find_owners": lambda: tools.find_owners("cartservice"),
        "find_experts": lambda: tools.find_experts("cartservice", 10000),
        "similar_incidents": lambda: tools.similar_incidents("cartservice"),
        "trace_decision": lambda: tools.trace_decision("cartservice"),
        "critical_services": tools.critical_services,
        "single_points_of_failure": tools.single_points_of_failure,
        "team_clusters": tools.team_clusters,
        "create_incident_issue": lambda: tools.create_incident_issue("cartservice", "Latency test"),
    }
    timings = {}
    for name, call in calls.items():
        samples = []
        for _ in range(3):
            start = perf_counter()
            result = call()
            samples.append((perf_counter() - start) * 1000)
            if name == "create_incident_issue":
                graph.query(
                    "MATCH (n) WHERE n.id IN $ids DETACH DELETE n",
                    {"ids": [result["data"]["incident_id"], result["data"]["issue_id"]]},
                )
        timings[name] = round(median(samples), 1)
    print("warm median milliseconds:", json.dumps(timings, sort_keys=True))
    # Network latency is external; report rather than make correctness tests flaky.


def test_disconnected_path(graph):
    graph.query(
        "CREATE (s:Service {id:$id, name:$name, synthetic:$synthetic, source_url:$url})",
        {"id": "svc:isolated", "name": "isolated", "synthetic": True, "url": "synthetic"},
    )
    try:
        result = tools.failure_path("cartservice", "isolated")
        assert check(result) == {"exists": False, "hops": None, "path_ids": []}
        assert len(result["path"]["nodes"]) == 2
        assert result["path"]["edges"] == []
    finally:
        graph.query("MATCH (s:Service {id:$id}) DETACH DELETE s", {"id": "svc:isolated"})


def test_criticality_stored(graph):
    ranked = tools.critical_services()["data"]["ranked"]
    stored = dict(graph.query("MATCH (s:Service) RETURN s.id, s.criticality", {}).result_set)
    assert stored == {row["id"]: row["score"] for row in ranked}

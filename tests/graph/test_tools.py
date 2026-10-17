import json

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
        "svc:frontend": 1, "svc:checkoutservice": 1}
    assert {e["target"] for e in result["path"]["edges"]} == {"svc:cartservice"}
    assert check(tools.blast_radius("cartservice", 0))["affected"] == []
    assert check(tools.blast_radius("frontend"))["affected"] == []


def test_experts(graph):
    result = tools.find_experts("cartservice", days=10000)
    assert check(result)["experts"] == [{"id": "person:alice", "name": "Alice Nguyen",
        "pr_count": 1, "last_touched": "2024-05-01T12:00:00Z"}]
    assert "pr:234" in {n["id"] for n in result["path"]["nodes"]}
    assert check(tools.find_experts("cartservice", days=0))["experts"] == []


def test_incidents(graph):
    result = tools.similar_incidents("cartservice")
    assert check(result)["incidents"][0]["relation"] == "CAUSED"
    assert len(result["data"]["incidents"]) == 1
    assert check(tools.similar_incidents("paymentservice"))["incidents"][0]["relation"] == "AFFECTED"


def test_decisions(graph):
    result = tools.trace_decision("cartservice")
    assert check(result)["decisions"][0]["id"] == "decision:use-grpc"
    assert "incident:inc-003" in {n["id"] for n in result["path"]["nodes"]}


@pytest.mark.parametrize("fn", [tools.blast_radius, tools.find_experts,
                                 tools.similar_incidents, tools.trace_decision])
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


@pytest.mark.parametrize("fn", [tools.critical_services, tools.single_points_of_failure, tools.team_clusters])
def test_fallback(graph, monkeypatch, fn):
    from graph import algorithms
    monkeypatch.setattr(algorithms, "_procedures", lambda graph: frozenset())
    result = fn()
    assert check(result)["method"] == "networkx-fallback"
    assert len(result["path"]["nodes"]) >= 5

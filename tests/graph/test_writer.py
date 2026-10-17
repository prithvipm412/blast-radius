import pytest

from graph import writer


def test_fixture_upserts_are_idempotent(graph, sample_graph):
    nodes = {}
    labels = {}
    for raw in sample_graph["nodes"]:
        record = {k: v for k, v in raw.items() if k != "label"}
        if raw["label"] == "Team":
            record["team_kind"] = "oncall"
        nodes.setdefault(raw["label"], []).append(record)
        labels[record["id"]] = raw["label"]
    before = graph.query("MATCH (n) RETURN count(n)", {}).result_set[0][0]
    for _ in range(2):
        for label, records in nodes.items():
            assert writer.upsert_nodes(label, records) == {"upserted": len(records)}
        for edge in sample_graph["edges"]:
            record = {k: v for k, v in edge.items() if k not in {"type", "source", "target"}}
            record.update(from_id=edge["source"], to_id=edge["target"])
            assert writer.upsert_edges(
                edge["type"], labels[edge["source"]], labels[edge["target"]], [record]
            ) == {"upserted": 1}
    assert graph.query("MATCH (n) RETURN count(n)", {}).result_set[0][0] == before
    assert graph.query("MATCH ()-[r]->() RETURN count(r)", {}).result_set[0][0] == len(
        sample_graph["edges"]
    )


def test_commit_custom_key_and_parameter_safety(graph):
    record = {
        "id": "commit:test-sha",
        "sha": "test-sha",
        "name": "x' SET n.pwned=true //",
        "source_url": "https://github.com/example/repo/commit/test-sha",
        "synthetic": False,
    }
    assert writer.upsert_nodes("Commit", [record], key="sha") == {"upserted": 1}
    assert writer.upsert_nodes("Commit", [{**record, "message": "updated"}], key="sha") == {
        "upserted": 1
    }
    rows = graph.query("MATCH (n:Commit {sha:$sha}) RETURN n", {"sha": "test-sha"}).result_set
    assert len(rows) == 1 and rows[0][0].properties["name"] == record["name"]
    assert "pwned" not in rows[0][0].properties
    assert writer.upsert_edges(
        "AUTHORED",
        "Person",
        "Commit",
        [{"from_id": "person:alice", "to_id": record["id"], "synthetic": False}],
    ) == {"upserted": 1}


def test_sync_metadata(graph):
    writer.set_sync_meta("2026-10-17T00:00:00Z", last_synced_commit_sha="abc")
    writer.set_sync_meta("2026-10-17T01:00:00Z", last_synced_issue_number=12)
    rows = graph.query("MATCH (n:SyncMeta) RETURN n", {}).result_set
    assert len(rows) == 1
    assert rows[0][0].properties == {
        "id": "meta:sync",
        "name": "sync metadata",
        "source_url": "internal",
        "synthetic": False,
        "operational": True,
        "last_synced_at": "2026-10-17T01:00:00Z",
        "last_synced_commit_sha": "abc",
        "last_synced_issue_number": 12,
    }
    with pytest.raises(ValueError, match="watermark"):
        writer.set_sync_meta("now", password="no")


def test_indexes(graph):
    writer.ensure_indexes()
    writer.ensure_indexes()
    assert len(graph.list_constraints()) == 12


def test_empty_and_invalid(graph):
    assert writer.upsert_nodes("Service", []) == {"upserted": 0}
    assert writer.upsert_edges("DEPENDS_ON", "Service", "Service", []) == {"upserted": 0}
    with pytest.raises(ValueError):
        writer.upsert_nodes("Service) DELETE n //", [])
    with pytest.raises(ValueError):
        writer.upsert_edges("AUTHORED", "Service", "Service", [])
    with pytest.raises(ValueError, match="synthetic"):
        writer.upsert_nodes(
            "Incident",
            [{"id": "incident:bad", "name": "bad", "source_url": "synthetic", "synthetic": False}],
        )
    with pytest.raises(ValueError, match="source_url"):
        writer.upsert_nodes(
            "Decision",
            [
                {
                    "id": "decision:bad",
                    "name": "bad",
                    "source_url": "ingest/data/file.json",
                    "synthetic": True,
                }
            ],
        )
    with pytest.raises(ValueError, match="synthetic"):
        writer.upsert_edges(
            "CITES",
            "Decision",
            "PR",
            [{"from_id": "decision:use-grpc", "to_id": "pr:234", "synthetic": False}],
        )


def test_missing_endpoint_is_atomic(graph):
    before = graph.query("MATCH ()-[r:DEPENDS_ON]->() RETURN count(r)", {}).result_set
    with pytest.raises(ValueError, match="missing endpoints"):
        writer.upsert_edges(
            "DEPENDS_ON",
            "Service",
            "Service",
            [
                {"from_id": "svc:frontend", "to_id": "svc:paymentservice", "synthetic": False},
                {"from_id": "svc:missing", "to_id": "svc:cartservice", "synthetic": False},
            ],
        )
    assert graph.query("MATCH ()-[r:DEPENDS_ON]->() RETURN count(r)", {}).result_set == before


def test_member_provenance(graph):
    with pytest.raises(ValueError, match="synthetic flags"):
        writer.upsert_edges(
            "MEMBER_OF",
            "Person",
            "Team",
            [{"from_id": "person:alice", "to_id": "team:payments", "synthetic": False}],
        )
    assert writer.upsert_edges(
        "MEMBER_OF",
        "Person",
        "Team",
        [{"from_id": "person:alice", "to_id": "team:payments", "synthetic": True}],
    ) == {"upserted": 1}

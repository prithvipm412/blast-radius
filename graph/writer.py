"""Ingest-facing bulk writes, scoped to the current FALKORDB_GRAPH."""

from graph.db import get_graph
from graph.schema import ensure_schema
from graph.write_queries import EDGE_QUERIES, KEYED_NODE_QUERIES, NODE_QUERIES


def ensure_indexes() -> None:
    """Idempotently ensure all contract indexes and uniqueness constraints."""
    ensure_schema(get_graph())


def _flags(record):
    if not isinstance(record.get("synthetic"), bool):
        raise ValueError("every record must include a boolean synthetic flag")
    if "operational" in record and not isinstance(record["operational"], bool):
        raise ValueError("operational must be a boolean")


def _node(label, record, key):
    record = dict(record)
    _flags(record)
    for prop in {"id", "name", "source_url", key}:
        if prop not in record or record[prop] is None:
            raise ValueError("node is missing required property: " + prop)
    if not isinstance(record["id"], str) or not record["id"]:
        raise ValueError("node id must be a nonempty string")
    expected = None
    if label in {"Service", "Repo", "File", "Commit", "PR", "SyncMeta"}:
        expected = False
    elif label in {"Incident", "Decision"}:
        expected = True
    elif label == "Team":
        kind = record.get("team_kind")
        if kind not in {"oncall", "github"}:
            raise ValueError("Team.team_kind must be oncall or github")
        expected = kind == "oncall"
    elif label == "Doc":
        kind = record.get("kind")
        if kind not in {"readme", "runbook", "postmortem"}:
            raise ValueError("invalid Doc.kind")
        expected = kind != "readme"
    if expected is not None and record["synthetic"] != expected:
        raise ValueError("synthetic flag conflicts with the node schema")
    if record["synthetic"] and label != "Issue" and record["source_url"] != "synthetic":
        raise ValueError("synthetic nodes must have source_url='synthetic'")
    if label == "SyncMeta":
        if (record["id"], record["name"], record["source_url"], record.get("operational")) != (
            "meta:sync",
            "sync metadata",
            "internal",
            True,
        ):
            raise ValueError("SyncMeta must use the singleton identity and operational=true")
    return record


def upsert_nodes(label: str, records: list[dict], key: str = "id") -> dict:
    """UNWIND/MERGE nodes by key, retaining existing properties absent from records."""
    if label not in NODE_QUERIES:
        raise ValueError("unknown node label: " + label)
    if not isinstance(key, str) or not key:
        raise ValueError("key must be a nonempty property name")
    normalized = [_node(label, record, key) for record in records]
    if not normalized:
        return {"upserted": 0}
    query = NODE_QUERIES[label] if key == "id" else KEYED_NODE_QUERIES[label]
    params = {"records": normalized}
    if key != "id":
        params["key"] = key
    rows = get_graph().query(query, params).result_set
    return {"upserted": rows[0][0]}


def upsert_edges(edge_type: str, from_label: str, to_label: str, records: list[dict]) -> dict:
    """UNWIND/MERGE a schema-valid edge batch; missing endpoints fail without writes."""
    query = EDGE_QUERIES.get((edge_type, from_label, to_label))
    if query is None:
        raise ValueError("unsupported edge type or endpoint labels")
    normalized = []
    for record in records:
        _flags(record)
        if not all(isinstance(record.get(k), str) and record[k] for k in ("from_id", "to_id")):
            raise ValueError("edges require nonempty from_id and to_id")
        expected = from_label in {"Incident", "Decision"} or (
            edge_type == "OWNS" and to_label == "Service"
        )
        if edge_type != "MEMBER_OF" and from_label != "Doc" and record["synthetic"] != expected:
            raise ValueError("synthetic flag conflicts with the edge schema")
        props = {k: v for k, v in record.items() if k not in {"from_id", "to_id"}}
        normalized.append({"from_id": record["from_id"], "to_id": record["to_id"], "props": props})
    if not normalized:
        return {"upserted": 0}
    rows = get_graph().query(query, {"records": normalized}).result_set
    count = rows[0][0] if rows else 0
    if count != len(normalized):
        raise ValueError("edge batch has missing endpoints or inconsistent synthetic flags")
    return {"upserted": count}


def set_sync_meta(last_synced_at: str, **watermarks) -> None:
    """Update the operational singleton without erasing unspecified watermarks."""
    if set(watermarks) - {"last_synced_commit_sha", "last_synced_issue_number"}:
        raise ValueError("unsupported sync watermark")
    upsert_nodes(
        "SyncMeta",
        [
            {
                "id": "meta:sync",
                "name": "sync metadata",
                "source_url": "internal",
                "synthetic": False,
                "operational": True,
                "last_synced_at": last_synced_at,
                **watermarks,
            }
        ],
    )

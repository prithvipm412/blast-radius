"""Public graph-tool contract. All graph answers come from FalkorDB."""

from datetime import datetime, timedelta, timezone

from graph import queries as q
from graph.db import get_graph
from graph.evidence import Evidence, node_dict

CAP = 2000


def _service_id(service):
    return service if ":" in service else "svc:" + service


def _run(query, params):
    rows = get_graph().query(query, params).result_set
    if len(rows) > CAP:
        raise ValueError("graph evidence exceeds 2000 rows; narrow the query")
    evidence = Evidence()
    evidence.add(rows)
    return rows, evidence


def _result(data, query, params, evidence):
    return {"data": data, "cypher": query, "params": params, "path": evidence.render()}


def _service_query(query, service, **kwargs):
    params = {"service": _service_id(service), "limit": CAP + 1, **kwargs}
    rows, evidence = _run(query, params)
    if not rows:
        raise ValueError(f"unknown service: {service}")
    return rows, evidence, params


def search_entities(text: str) -> dict:
    """Find entities of any label by case-insensitive name/id substring; up to 50 matches."""
    params = {"text": text.casefold(), "limit": 50}
    rows, evidence = _run(q.SEARCH, params)
    return _result({"matches": [node_dict(r[0]) for r in rows]}, q.SEARCH, params, evidence)


def blast_radius(service: str, max_depth: int = 4) -> dict:
    """Find callers affected by a service outage, walking incoming dependencies up to max_depth."""
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 0:
        raise ValueError("max_depth must be a nonnegative integer")
    rows, evidence, params = _service_query(q.BLAST, service, max_depth=max_depth)
    affected = {}
    for _, path, affected_node in rows:
        if path is not None:
            node = affected_node.properties
            affected[node["id"]] = {"id": node["id"], "name": node["name"],
                                    "depth": path.edge_count(), "synthetic": node["synthetic"]}
    data = {"root": params["service"],
            "affected": sorted(affected.values(), key=lambda n: (n["depth"], n["id"]))}
    return _result(data, q.BLAST, params, evidence)


def find_experts(service: str, days: int = 180) -> dict:
    """Rank contributors by distinct recently merged PRs; path includes PR/file evidence and authors."""
    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        raise ValueError("days must be a nonnegative integer")
    now = datetime.now(timezone.utc)
    stamp = lambda dt: dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows, evidence, params = _service_query(
        q.EXPERTS, service, cutoff=stamp(now - timedelta(days=days)), now=stamp(now))
    experts = {}
    for _, path in rows:
        if path is None:
            continue
        _, _, pr, person = path.nodes()
        props, change = person.properties, pr.properties
        entry = experts.setdefault(props["id"], {"id": props["id"], "name": props["name"],
                                                "prs": {}, "last_touched": change["merged_at"]})
        entry["prs"][change["id"]] = change
        entry["last_touched"] = max(entry["last_touched"], change["merged_at"])
    ranked = [{"id": e["id"], "name": e["name"], "pr_count": len(e["prs"]),
               "last_touched": e["last_touched"]} for e in experts.values()]
    ranked.sort(key=lambda e: (-e["pr_count"], e["id"]))
    return _result({"experts": ranked}, q.EXPERTS, params, evidence)


def similar_incidents(service: str) -> dict:
    """Find incidents on this service or a one-hop dependency neighbor, newest first."""
    rows, evidence, params = _service_query(q.INCIDENTS, service)
    incidents = {}
    for _, neighborhood, path in rows:
        if path is None:
            continue
        incident = path.first_node().properties
        relation = path.edges()[0].relation
        priority = (neighborhood.edge_count(), relation != "CAUSED")
        if incident["id"] not in incidents or priority < incidents[incident["id"]][0]:
            incidents[incident["id"]] = (priority, {
                **{k: incident.get(k) for k in ("id", "name", "severity", "started_at")},
                "relation": relation})
    result = sorted((v[1] for v in incidents.values()),
                    key=lambda i: (i["started_at"] or "", i["id"]), reverse=True)
    return _result({"incidents": result}, q.INCIDENTS, params, evidence)


def trace_decision(service: str) -> dict:
    """Trace decisions governing a service, cited implementation PRs and incident context."""
    rows, evidence, params = _service_query(q.DECISIONS, service)
    decisions = {}
    for _, path, citation, _ in rows:
        if path is None:
            continue
        props = path.first_node().properties
        entry = decisions.setdefault(props["id"], {
            **{k: props.get(k) for k in ("id", "name", "status", "decided_at")}, "cites_prs": []})
        if citation:
            pr_id = citation.last_node().properties["id"]
            if pr_id not in entry["cites_prs"]:
                entry["cites_prs"].append(pr_id)
    for entry in decisions.values():
        entry["cites_prs"].sort()
    return _result({"decisions": list(decisions.values())}, q.DECISIONS, params, evidence)


def critical_services() -> dict:
    """Rank Service dependencies by native PageRank; exports real edges for highlighting."""
    from graph.algorithms import run_algorithm
    return run_algorithm("pagerank", _run, _result, CAP)


def single_points_of_failure() -> dict:
    """Rank services by native betweenness; fall back to NetworkX only if unavailable."""
    from graph.algorithms import run_algorithm
    return run_algorithm("betweenness", _run, _result, CAP)


def team_clusters() -> dict:
    """Detect service communities via native label propagation and label them by owning team."""
    from graph.algorithms import run_algorithm
    return run_algorithm("clusters", _run, _result, CAP)

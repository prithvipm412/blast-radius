"""Public graph-tool contract. All graph answers come from FalkorDB."""

from datetime import UTC, datetime, timedelta

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
            affected[node["id"]] = {
                "id": node["id"],
                "name": node["name"],
                "depth": path.edge_count(),
                "synthetic": node["synthetic"],
            }
    data = {
        "root": params["service"],
        "affected": sorted(affected.values(), key=lambda n: (n["depth"], n["id"])),
    }
    return _result(data, q.BLAST, params, evidence)


_BOT_EXACT = {"renovate-bot", "dependabot", "github-actions"}


def _is_bot(name: str | None) -> bool:
    v = (name or "").lower()
    return bool(v) and (v in _BOT_EXACT or v.endswith("[bot]") or v.endswith("-bot"))


def _rank_experts(rows):
    experts: dict[str, dict] = {}
    kept_paths = []
    for _, path in rows:
        if path is None:
            continue
        _, _, pr, person = path.nodes()
        props, change = person.properties, pr.properties
        if _is_bot(props.get("github_login")) or _is_bot(props.get("name")):
            continue
        kept_paths.append(path)
        entry = experts.setdefault(
            props["id"],
            {
                "id": props["id"],
                "name": props["name"],
                "prs": {},
                "last_touched": change["merged_at"],
            },
        )
        entry["prs"][change["id"]] = change
        entry["last_touched"] = max(entry["last_touched"], change["merged_at"])
    ranked = sorted(
        (
            {
                "id": e["id"],
                "name": e["name"],
                "pr_count": len(e["prs"]),
                "last_touched": e["last_touched"],
            }
            for e in experts.values()
        ),
        key=lambda e: (-e["pr_count"], e["id"]),
    )
    return ranked, kept_paths


def find_experts(service: str, days: int = 180) -> dict:
    """Rank human contributors (automation accounts excluded) by distinct recently merged
    PRs. If fewer than 3 humans turn up within `days`, widen to all-time rather than
    reporting a near-empty, misleading result. Only the kept (human) PR/File evidence is
    added to the returned path - not every PR the underlying query touched."""
    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        raise ValueError("days must be a nonnegative integer")
    now = datetime.now(UTC)
    stamp = lambda dt: dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows, _, params = _service_query(
        q.EXPERTS, service, cutoff=stamp(now - timedelta(days=days)), now=stamp(now)
    )
    root = rows[0][0]
    ranked, kept_paths = _rank_experts(rows)
    if len(ranked) < 3:
        rows, _, params = _service_query(
            q.EXPERTS, service, cutoff="0000-01-01T00:00:00Z", now=stamp(now)
        )
        ranked, kept_paths = _rank_experts(rows)

    evidence = Evidence()
    evidence.add(root)
    for path in kept_paths:
        evidence.add(path)
    return _result({"experts": ranked}, q.EXPERTS, params, evidence)


def similar_incidents(service: str) -> dict:
    """Top 5 incidents on this service or a one-hop dependency neighbor: same-service
    incidents first, then downstream-neighbor incidents, most recent first within each
    group. Only the 5 kept incidents' nodes/edges are added to the returned path - not
    every incident the underlying query happened to touch."""
    rows, _, params = _service_query(q.INCIDENTS, service)
    root = rows[0][0]
    best: dict[str, tuple] = {}
    for _, neighborhood, path in rows:
        if path is None:
            continue
        incident = path.first_node().properties
        relation = path.edges()[0].relation
        same_service = neighborhood.edge_count() == 0
        rank = (0 if same_service else 1, incident.get("started_at") or "")
        current = best.get(incident["id"])
        if current is None or rank < current[0]:
            best[incident["id"]] = (rank, relation, path)

    # Stable two-pass sort: most-recent-first within each group, then same-service-first
    # across groups - a single sort can't mix an ascending and a descending key cleanly.
    by_recency = sorted(best.values(), key=lambda v: v[0][1], reverse=True)
    top5 = sorted(by_recency, key=lambda v: v[0][0])[:5]

    evidence = Evidence()
    evidence.add(root)
    incidents = []
    for _, relation, path in top5:
        evidence.add(path)
        incident = path.first_node().properties
        incidents.append(
            {
                **{k: incident.get(k) for k in ("id", "name", "severity", "started_at")},
                "relation": relation,
            }
        )
    return _result({"incidents": incidents}, q.INCIDENTS, params, evidence)


def trace_decision(service: str) -> dict:
    """Trace decisions governing a service, cited implementation PRs and incident context."""
    rows, evidence, params = _service_query(q.DECISIONS, service)
    decisions = {}
    for _, path, citation, _ in rows:
        if path is None:
            continue
        props = path.first_node().properties
        entry = decisions.setdefault(
            props["id"],
            {**{k: props.get(k) for k in ("id", "name", "status", "decided_at")}, "cites_prs": []},
        )
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


def find_owners(service: str) -> dict:
    """Find a service's owning team(s) and their members, with ownership/membership evidence.

    A service may be owned by more than one team (e.g. primary + secondary OWNS). `data.teams`
    lists every owning team with its own members. `data.team`/`data.members` stay single-team
    shaped (the first owning team, by id) so existing single-team callers keep working unchanged.
    """
    rows, evidence, params = _service_query(q.OWNERS, service)
    teams = {}
    for _, ownership, membership in rows:
        if ownership:
            props = ownership.first_node().properties
            teams.setdefault(props["id"], {"id": props["id"], "name": props["name"], "members": {}})
        if membership:
            person_props = membership.first_node().properties
            team_props = membership.last_node().properties
            entry = teams.setdefault(
                team_props["id"],
                {"id": team_props["id"], "name": team_props["name"], "members": {}},
            )
            entry["members"][person_props["id"]] = {
                k: person_props.get(k) for k in ("id", "name", "github_login")
            }
    teams_list = [
        {"id": t["id"], "name": t["name"], "members": list(t["members"].values())}
        for t in sorted(teams.values(), key=lambda t: t["id"])
    ]
    primary = teams_list[0] if teams_list else None
    data = {
        "team": {"id": primary["id"], "name": primary["name"]} if primary else None,
        "members": primary["members"] if primary else [],
        "teams": teams_list,
    }
    return _result(data, q.OWNERS, params, evidence)


def _undirected_failure_path(from_id, to_id):
    """BFS over the Service/DEPENDS_ON subgraph ignoring edge direction.

    FalkorDB doesn't support undirected shortestPath(), so this fetches the (small, capped)
    subgraph as real node/edge objects and searches in Python - the returned nodes/edges are
    the same FalkorDB objects graph.evidence.Evidence expects, so the rendered path stays
    exact (only the nodes/edges actually on the path), not the whole subgraph.
    """
    rows, sub_evidence = _run(q.DEPENDS_EDGES, {"limit": CAP + 1})
    node_by_id, adjacency, edge_by_pair = {}, {}, {}
    for s_node, edge, t_node in rows:
        sid, tid = s_node.properties["id"], t_node.properties["id"]
        node_by_id[sid], node_by_id[tid] = s_node, t_node
        adjacency.setdefault(sid, []).append(tid)
        adjacency.setdefault(tid, []).append(sid)
        edge_by_pair[(sid, tid)] = edge
        edge_by_pair[(tid, sid)] = edge

    prev = {from_id: None}
    queue = [from_id]
    while queue:
        cur, queue = queue[0], queue[1:]
        if cur == to_id:
            break
        for nxt in adjacency.get(cur, []):
            if nxt not in prev:
                prev[nxt] = cur
                queue.append(nxt)
    if to_id not in prev:
        return None

    ids, cur = [to_id], to_id
    while prev[cur] is not None:
        cur = prev[cur]
        ids.append(cur)
    ids.reverse()

    path_nodes = [node_by_id[i] for i in ids]
    path_edges = [edge_by_pair[(ids[i], ids[i + 1])] for i in range(len(ids) - 1)]
    return ids, path_nodes, path_edges


def failure_path(from_service: str, to_service: str) -> dict:
    """Trace failure propagation along incoming dependencies; same-service paths have zero hops."""
    params = {
        "from_service": _service_id(from_service),
        "to_service": _service_id(to_service),
        "limit": 1,
    }
    rows, evidence = _run(q.FAILURE, params)
    a, b, path = rows[0]
    for node, original in ((a, from_service), (b, to_service)):
        if node is None:
            raise ValueError(f"unknown service: {original}")
    if a.properties["id"] == b.properties["id"]:
        data = {"exists": True, "hops": 0, "path_ids": [a.properties["id"]]}
    elif path is not None:
        ids = [node.properties["id"] for node in path.nodes()]
        if ids[0] != a.properties["id"]:
            ids.reverse()
        data = {"exists": True, "hops": path.edge_count(), "path_ids": ids}
    else:
        # No directed incoming-dependency chain from a to b. They may still be connected
        # when direction is ignored (e.g. two services share a common dependency) - fall
        # back to an undirected path and say so explicitly via data["direction"], rather
        # than either fabricating a directed claim or reporting a false negative.
        fallback = _undirected_failure_path(a.properties["id"], b.properties["id"])
        if fallback is None:
            data = {"exists": False, "hops": None, "path_ids": []}
        else:
            ids, path_nodes, path_edges = fallback
            evidence.add(path_nodes)
            evidence.add(path_edges)
            data = {"exists": True, "hops": len(ids) - 1, "path_ids": ids, "direction": "undirected"}
    return _result(data, q.FAILURE, params, evidence)


def create_incident_issue(service: str, summary: str, dry_run: bool = True) -> dict:
    """Draft a cited incident report; filing a real issue requires GITHUB_ISSUE_REPO.

    Dry runs (the default) are UI-only and never write to FalkorDB - the Incident/Issue
    in `data` describe what a real filing would create, not a persisted node. Real filing
    (dry_run=False) does write synthetic Incident/Issue nodes, and never targets the
    upstream repo.
    """
    from graph.issues import create_issue

    return create_issue(service, summary, dry_run)

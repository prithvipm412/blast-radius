"""Tool registry for the agent loop.

Implements every function in contracts/tools.md with its exact signature and
return envelope ({"data", "cypher", "params", "path"}), backed by
tests/fixtures/sample_graph.json rather than a live FalkorDB connection.

Swap-in: once graph/ (Codex 2's branch) merges `graph/tools.py` onto main,
these stubs are replaced automatically — the import block below prefers
`graph.tools` and only falls back to the stubs defined in this file if that
import fails. No other code (agent/loop.py, api/main.py) needs to change.
Set TOOL_BACKEND=stub in .env to force the stub implementations even once
graph.tools exists (useful for isolated agent/api development).
"""

from __future__ import annotations

import json
import math
import os
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_graph.json"

_FORCE_STUB = os.environ.get("TOOL_BACKEND", "").lower() == "stub"
_BACKEND = "stub"

if not _FORCE_STUB:
    try:
        from graph.tools import (  # type: ignore
            blast_radius,
            create_incident_issue,
            critical_services,
            failure_path,
            find_experts,
            find_owners,
            search_entities,
            similar_incidents,
            single_points_of_failure,
            team_clusters,
            trace_decision,
        )

        _BACKEND = "graph"
    except ImportError:
        _BACKEND = "stub"

if _BACKEND == "stub":

    class _Graph:
        """Minimal in-memory graph loaded from the fixture, indexed for the stub tools below."""

        def __init__(self, path: Path = _FIXTURE_PATH):
            raw = json.loads(path.read_text())
            self.nodes: dict[str, dict] = {n["id"]: n for n in raw["nodes"]}
            self.edges: list[dict] = raw["edges"]
            self._out: dict[str, list[dict]] = {}
            self._in: dict[str, list[dict]] = {}
            for e in self.edges:
                self._out.setdefault(e["source"], []).append(e)
                self._in.setdefault(e["target"], []).append(e)

        def out_edges(self, node_id: str, type: str | None = None) -> list[dict]:
            return [e for e in self._out.get(node_id, []) if type is None or e["type"] == type]

        def in_edges(self, node_id: str, type: str | None = None) -> list[dict]:
            return [e for e in self._in.get(node_id, []) if type is None or e["type"] == type]

        def node(self, node_id: str) -> dict | None:
            return self.nodes.get(node_id)

        def add_edge(self, edge: dict) -> None:
            self.edges.append(edge)
            self._out.setdefault(edge["source"], []).append(edge)
            self._in.setdefault(edge["target"], []).append(edge)

        def resolve_service(self, service: str) -> str:
            sid = service if ":" in service else f"svc:{service}"
            node = self.nodes.get(sid)
            if node is None or node["label"] != "Service":
                raise ValueError(f"unknown service: {service}")
            return sid

        def resolve_node(self, ref: str) -> str:
            if ref in self.nodes:
                return ref
            candidate = f"svc:{ref}"
            if candidate in self.nodes:
                return candidate
            raise ValueError(f"unknown node: {ref}")

    _graph = _Graph()

    def _node_ref(node_id: str) -> dict:
        n = _graph.node(node_id)
        return {"id": node_id, "label": n["label"], "name": n["name"], "synthetic": n["synthetic"]}

    def _edge_ref(e: dict) -> dict:
        return {"source": e["source"], "target": e["target"], "type": e["type"], "synthetic": e["synthetic"]}

    def _path(node_ids: list[str], edges: list[dict]) -> dict:
        nodes = {nid: _node_ref(nid) for nid in node_ids}
        seen: set[tuple[str, str, str]] = set()
        out_edges = []
        for e in edges:
            key = (e["source"], e["target"], e["type"])
            if key not in seen:
                seen.add(key)
                out_edges.append(_edge_ref(e))
        return {"nodes": list(nodes.values()), "edges": out_edges}

    def _service_subgraph() -> tuple[list[str], list[dict]]:
        service_ids = [n["id"] for n in _graph.nodes.values() if n["label"] == "Service"]
        edges = [e for e in _graph.edges if e["type"] == "DEPENDS_ON"]
        return service_ids, edges

    def _pagerank(node_ids: list[str], edges: list[dict], damping: float = 0.85, iters: int = 50) -> dict[str, float]:
        n = len(node_ids)
        if n == 0:
            return {}
        outgoing: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for e in edges:
            if e["source"] in outgoing:
                outgoing[e["source"]].append(e["target"])
        scores = {nid: 1.0 / n for nid in node_ids}
        for _ in range(iters):
            new_scores = {nid: (1 - damping) / n for nid in node_ids}
            for nid in node_ids:
                out_links = outgoing[nid]
                if not out_links:
                    share = damping * scores[nid] / n
                    for t in node_ids:
                        new_scores[t] += share
                    continue
                share = damping * scores[nid] / len(out_links)
                for t in out_links:
                    if t in new_scores:
                        new_scores[t] += share
            scores = new_scores
        return scores

    def _betweenness(node_ids: list[str], edges: list[dict]) -> dict[str, float]:
        """Brandes' algorithm over the subgraph treated as undirected."""
        adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for e in edges:
            if e["source"] in adj and e["target"] in adj:
                adj[e["source"]].append(e["target"])
                adj[e["target"]].append(e["source"])

        betweenness = {nid: 0.0 for nid in node_ids}
        for s in node_ids:
            dist: dict[str, int] = {s: 0}
            preds: dict[str, list[str]] = {s: []}
            sigma: dict[str, int] = {s: 1}
            order: list[str] = []
            queue: deque[str] = deque([s])
            while queue:
                v = queue.popleft()
                order.append(v)
                for w in adj[v]:
                    if w not in dist:
                        dist[w] = dist[v] + 1
                        queue.append(w)
                    if dist.get(w) == dist[v] + 1:
                        sigma[w] = sigma.get(w, 0) + sigma[v]
                        preds.setdefault(w, []).append(v)
            delta = {v: 0.0 for v in order}
            for w in reversed(order):
                for v in preds.get(w, []):
                    delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
                if w != s:
                    betweenness[w] += delta[w]
        for nid in betweenness:
            betweenness[nid] /= 2  # each pair counted from both endpoints
        return betweenness

    def search_entities(text: str) -> dict:
        needle = text.lower()
        matches = [
            n for n in _graph.nodes.values() if needle in n["name"].lower() or needle in n["id"].lower()
        ]
        data = {
            "matches": [
                {"id": n["id"], "label": n["label"], "name": n["name"], "synthetic": n["synthetic"]}
                for n in matches
            ]
        }
        return {
            "data": data,
            "cypher": (
                "MATCH (n) WHERE toLower(n.name) CONTAINS toLower($text) "
                "OR toLower(n.id) CONTAINS toLower($text) RETURN n"
            ),
            "params": {"text": text},
            "path": _path([n["id"] for n in matches], []),
        }

    def blast_radius(service: str, max_depth: int = 4) -> dict:
        root = _graph.resolve_service(service)
        visited = {root: 0}
        frontier = [root]
        touched_edges: list[dict] = []
        depth = 0
        while frontier and depth < max_depth:
            depth += 1
            next_frontier = []
            for nid in frontier:
                for e in _graph.in_edges(nid, "DEPENDS_ON"):
                    touched_edges.append(e)
                    src = e["source"]
                    if src not in visited:
                        visited[src] = depth
                        next_frontier.append(src)
            frontier = next_frontier

        affected = sorted(
            (
                {"id": nid, "name": _graph.node(nid)["name"], "depth": d, "synthetic": _graph.node(nid)["synthetic"]}
                for nid, d in visited.items()
                if nid != root
            ),
            key=lambda a: a["depth"],
        )
        return {
            "data": {"root": root, "affected": affected},
            # Cypher variable-length path bounds must be literal integers, not parameters.
            "cypher": (
                f"MATCH (root:Service {{id: $service}})<-[:DEPENDS_ON*1..{max_depth}]-(dep:Service) "
                "RETURN DISTINCT dep"
            ),
            "params": {"service": root},
            "path": _path(list(visited.keys()), touched_edges),
        }

    def failure_path(from_service: str, to_service: str) -> dict:
        src = _graph.resolve_service(from_service)
        dst = _graph.resolve_service(to_service)

        adj: dict[str, list[tuple[str, dict]]] = {}
        for e in _graph.edges:
            if e["type"] != "DEPENDS_ON":
                continue
            adj.setdefault(e["source"], []).append((e["target"], e))
            adj.setdefault(e["target"], []).append((e["source"], e))

        prev: dict[str, tuple[str, dict] | None] = {src: None}
        queue: deque[str] = deque([src])
        while queue:
            cur = queue.popleft()
            if cur == dst:
                break
            for nxt, e in adj.get(cur, []):
                if nxt not in prev:
                    prev[nxt] = (cur, e)
                    queue.append(nxt)

        cypher = "MATCH p = shortestPath((a:Service {id: $from})-[:DEPENDS_ON*]-(b:Service {id: $to})) RETURN p"
        params = {"from": src, "to": dst}

        if dst not in prev:
            return {
                "data": {"exists": False, "hops": None, "path_ids": []},
                "cypher": cypher,
                "params": params,
                "path": _path([src, dst], []),
            }

        path_ids = [dst]
        path_edges = []
        cur = dst
        while prev[cur] is not None:
            parent, e = prev[cur]
            path_edges.append(e)
            path_ids.append(parent)
            cur = parent
        path_ids.reverse()
        path_edges.reverse()

        return {
            "data": {"exists": True, "hops": len(path_ids) - 1, "path_ids": path_ids},
            "cypher": cypher,
            "params": params,
            "path": _path(path_ids, path_edges),
        }

    def find_owners(service: str) -> dict:
        sid = _graph.resolve_service(service)
        cypher = (
            "MATCH (t:Team)-[:OWNS]->(s:Service {id: $service}) "
            "OPTIONAL MATCH (p:Person)-[:MEMBER_OF]->(t) RETURN t, p"
        )
        params = {"service": sid}

        owns_edges = _graph.in_edges(sid, "OWNS")
        if not owns_edges:
            return {"data": {"team": None, "members": []}, "cypher": cypher, "params": params, "path": _path([sid], [])}

        team_edge = owns_edges[0]
        team_id = team_edge["source"]
        team = _graph.node(team_id)
        touched_edges = [team_edge]
        nodes = [sid, team_id]
        members = []
        for e in _graph.in_edges(team_id, "MEMBER_OF"):
            person = _graph.node(e["source"])
            members.append({"id": person["id"], "name": person["name"], "github_login": person.get("github_login")})
            touched_edges.append(e)
            nodes.append(person["id"])

        return {
            "data": {"team": {"id": team["id"], "name": team["name"]}, "members": members},
            "cypher": cypher,
            "params": params,
            "path": _path(nodes, touched_edges),
        }

    def find_experts(service: str, days: int = 180) -> dict:
        sid = _graph.resolve_service(service)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        file_edges = _graph.out_edges(sid, "CONTAINS")
        touched_edges = list(file_edges)
        nodes: set[str] = {sid}
        counts: dict[str, dict] = {}

        for fe in file_edges:
            file_id = fe["target"]
            nodes.add(file_id)
            for te in _graph.in_edges(file_id, "TOUCHED"):
                pr = _graph.node(te["source"])
                merged_at = pr.get("merged_at")
                if not merged_at:
                    continue
                merged_dt = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
                if merged_dt < cutoff:
                    continue
                touched_edges.append(te)
                nodes.add(pr["id"])
                for ae in _graph.in_edges(pr["id"], "AUTHORED"):
                    person = _graph.node(ae["source"])
                    touched_edges.append(ae)
                    nodes.add(person["id"])
                    entry = counts.setdefault(
                        person["id"],
                        {"id": person["id"], "name": person["name"], "pr_count": 0, "last_touched": merged_at},
                    )
                    entry["pr_count"] += 1
                    if merged_at > entry["last_touched"]:
                        entry["last_touched"] = merged_at

        experts = sorted(counts.values(), key=lambda e: e["pr_count"], reverse=True)
        return {
            "data": {"experts": experts},
            "cypher": (
                "MATCH (s:Service {id: $service})-[:CONTAINS]->(f:File)<-[:TOUCHED]-(pr:PR) "
                "WHERE pr.merged_at >= $cutoff "
                "MATCH (person:Person)-[:AUTHORED]->(pr) "
                "RETURN person, count(pr) AS pr_count, max(pr.merged_at) AS last_touched "
                "ORDER BY pr_count DESC"
            ),
            "params": {"service": sid, "cutoff": cutoff.isoformat()},
            "path": _path(list(nodes), touched_edges),
        }

    def similar_incidents(service: str) -> dict:
        sid = _graph.resolve_service(service)
        neighbor_ids = {sid}
        for e in _graph.out_edges(sid, "DEPENDS_ON"):
            neighbor_ids.add(e["target"])
        for e in _graph.in_edges(sid, "DEPENDS_ON"):
            neighbor_ids.add(e["source"])

        incidents = []
        touched_edges = []
        nodes: set[str] = {sid}
        for e in _graph.edges:
            if e["type"] in ("CAUSED", "AFFECTED") and e["target"] in neighbor_ids:
                incident = _graph.node(e["source"])
                incidents.append(
                    {
                        "id": incident["id"],
                        "name": incident["name"],
                        "severity": incident.get("severity"),
                        "started_at": incident.get("started_at"),
                        "relation": e["type"],
                    }
                )
                touched_edges.append(e)
                nodes.add(e["source"])
                nodes.add(e["target"])

        incidents.sort(key=lambda i: i["started_at"] or "", reverse=True)
        return {
            "data": {"incidents": incidents},
            "cypher": (
                "MATCH (s:Service {id: $service}) "
                "OPTIONAL MATCH (s)-[:DEPENDS_ON]-(n:Service) "
                "WITH collect(DISTINCT s) + collect(DISTINCT n) AS neighborhood "
                "UNWIND neighborhood AS svc "
                "MATCH (i:Incident)-[r:CAUSED|AFFECTED]->(svc) "
                "RETURN i, type(r) AS relation, svc ORDER BY i.started_at DESC"
            ),
            "params": {"service": sid},
            "path": _path(list(nodes), touched_edges),
        }

    def trace_decision(service: str) -> dict:
        sid = _graph.resolve_service(service)
        decided_edges = _graph.in_edges(sid, "DECIDED")
        touched_edges = list(decided_edges)
        nodes: set[str] = {sid}
        decisions = []

        for e in decided_edges:
            decision = _graph.node(e["source"])
            nodes.add(decision["id"])
            cites_prs = []
            for ce in _graph.out_edges(decision["id"], "CITES"):
                target = _graph.node(ce["target"])
                if target["label"] == "PR":
                    cites_prs.append(target["id"])
                    touched_edges.append(ce)
                    nodes.add(target["id"])
            decisions.append(
                {
                    "id": decision["id"],
                    "name": decision["name"],
                    "status": decision.get("status"),
                    "decided_at": decision.get("decided_at"),
                    "cites_prs": cites_prs,
                }
            )

        return {
            "data": {"decisions": decisions},
            "cypher": (
                "MATCH (d:Decision)-[:DECIDED]->(s:Service {id: $service}) "
                "OPTIONAL MATCH (d)-[:CITES]->(pr:PR) RETURN d, pr"
            ),
            "params": {"service": sid},
            "path": _path(list(nodes), touched_edges),
        }

    def critical_services() -> dict:
        service_ids, edges = _service_subgraph()
        scores = _pagerank(service_ids, edges)
        ranked = [
            {"id": sid, "name": _graph.node(sid)["name"], "score": round(score, 4)}
            for sid, score in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        ]
        return {
            "data": {"ranked": ranked},
            "cypher": (
                "CALL algo.pageRank('Service', 'DEPENDS_ON') YIELD node, score "
                "RETURN node, score ORDER BY score DESC "
                "-- STUB: computed via in-process power-iteration PageRank over the fixture, "
                "not a real FalkorDB algo call"
            ),
            "params": {},
            "path": _path(service_ids, edges),
        }

    def single_points_of_failure() -> dict:
        service_ids, edges = _service_subgraph()
        scores = _betweenness(service_ids, edges)
        ranked = [
            {"id": sid, "name": _graph.node(sid)["name"], "score": round(score, 4)}
            for sid, score in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        ]
        return {
            "data": {"ranked": ranked},
            "cypher": (
                "CALL algo.betweenness('Service', 'DEPENDS_ON') YIELD node, score "
                "RETURN node, score ORDER BY score DESC "
                "-- STUB: computed via in-process Brandes' algorithm over the fixture, "
                "not a real FalkorDB algo call"
            ),
            "params": {},
            "path": _path(service_ids, edges),
        }

    def team_clusters() -> dict:
        service_ids, edges = _service_subgraph()
        adj: dict[str, list[str]] = {nid: [] for nid in service_ids}
        for e in edges:
            if e["source"] in adj and e["target"] in adj:
                adj[e["source"]].append(e["target"])
                adj[e["target"]].append(e["source"])

        visited: set[str] = set()
        clusters = []
        cluster_id = 0
        for nid in service_ids:
            if nid in visited:
                continue
            comp = []
            queue: deque[str] = deque([nid])
            visited.add(nid)
            while queue:
                v = queue.popleft()
                comp.append(v)
                for w in adj[v]:
                    if w not in visited:
                        visited.add(w)
                        queue.append(w)

            team_counts: dict[str, int] = {}
            for sid in comp:
                for e in _graph.in_edges(sid, "OWNS"):
                    team_counts[e["source"]] = team_counts.get(e["source"], 0) + 1
            dominant_team = max(team_counts, key=team_counts.get) if team_counts else None

            clusters.append({"cluster_id": cluster_id, "services": comp, "dominant_team": dominant_team})
            cluster_id += 1

        return {
            "data": {"clusters": clusters},
            "cypher": (
                "CALL algo.louvain('Service', 'DEPENDS_ON') YIELD node, community "
                "RETURN node, community "
                "-- STUB: computed via in-process connected-components over the fixture, "
                "not a real FalkorDB algo call"
            ),
            "params": {},
            "path": _path(service_ids, edges),
        }

    def create_incident_issue(service: str, summary: str, dry_run: bool = True) -> dict:
        sid = _graph.resolve_service(service)
        now = datetime.now(timezone.utc)
        short_name = sid.split(":", 1)[1]
        incident_id = f"incident:inc-{now:%Y-%m-%d}-{short_name}-{uuid.uuid4().hex[:6]}"
        title = f"[Blast Radius] Incident: {short_name}"

        # STUB: real GitHub filing (dry_run=False) belongs to graph.tools once merged
        # (needs GITHUB_TOKEN + GITHUB_REPO). The stub always drafts, never files.
        issue_id = f"issue:draft-{uuid.uuid4().hex[:8]}"
        url = "draft"

        new_incident = {
            "label": "Incident",
            "id": incident_id,
            "name": f"Incident: {short_name}",
            "source_url": "synthetic",
            "synthetic": True,
            "summary": summary,
            "severity": "sev3",
            "started_at": now.isoformat(),
            "resolved_at": None,
        }
        _graph.nodes[incident_id] = new_incident
        caused_edge = {"type": "CAUSED", "source": incident_id, "target": sid, "synthetic": True}
        _graph.add_edge(caused_edge)

        return {
            "data": {"issue_id": issue_id, "dry_run": dry_run, "url": url, "incident_id": incident_id, "title": title},
            "cypher": (
                "CREATE (i:Incident {id: $incident_id, name: $name, summary: $summary, synthetic: true}) "
                "WITH i MATCH (s:Service {id: $service}) CREATE (i)-[:CAUSED]->(s) RETURN i"
            ),
            "params": {"incident_id": incident_id, "name": new_incident["name"], "summary": summary, "service": sid},
            "path": _path([incident_id, sid], [caused_edge]),
        }

    def graph_neighborhood(
        focus: str | None = None, depth: int = 2, cap: int = 500, scope: str = "overview"
    ) -> dict:
        """Backs GET /api/graph. Not one of contracts/tools.md's 11 agent tools —
        a plain graph-read helper used directly by api/main.py."""
        if focus is None and scope == "overview":
            service_ids = [n["id"] for n in _graph.nodes.values() if n["label"] == "Service"]
            team_ids = [n["id"] for n in _graph.nodes.values() if n["label"] == "Team"]
            node_ids = service_ids + team_ids
            node_id_set = set(node_ids)
            edges = [
                e
                for e in _graph.edges
                if e["type"] in ("DEPENDS_ON", "OWNS")
                and e["source"] in node_id_set
                and e["target"] in node_id_set
            ]
            return _path(node_ids, edges)

        if focus is None:  # scope == "all"
            node_ids = list(_graph.nodes.keys())[:cap]
            node_id_set = set(node_ids)
            edges = [e for e in _graph.edges if e["source"] in node_id_set and e["target"] in node_id_set]
            return _path(node_ids, edges)

        fid = _graph.resolve_node(focus)
        visited = {fid}
        touched_edges: list[dict] = []
        frontier = [fid]
        for _ in range(max(depth, 0)):
            next_frontier = []
            for nid in frontier:
                for e in _graph.out_edges(nid) + _graph.in_edges(nid):
                    touched_edges.append(e)
                    other = e["target"] if e["source"] == nid else e["source"]
                    if other not in visited:
                        visited.add(other)
                        next_frontier.append(other)
            frontier = next_frontier
        return _path(list(visited)[:cap], touched_edges)

    def graph_stats() -> dict:
        """Backs GET /api/stats."""
        nodes_by_label: dict[str, int] = {}
        synthetic_count = 0
        real_count = 0
        for n in _graph.nodes.values():
            nodes_by_label[n["label"]] = nodes_by_label.get(n["label"], 0) + 1
            if n["synthetic"]:
                synthetic_count += 1
            else:
                real_count += 1
        edges_by_type: dict[str, int] = {}
        for e in _graph.edges:
            edges_by_type[e["type"]] = edges_by_type.get(e["type"], 0) + 1
        return {
            "nodes_by_label": nodes_by_label,
            "edges_by_type": edges_by_type,
            "synthetic_node_count": synthetic_count,
            "real_node_count": real_count,
            "last_synced_at": None,
        }

else:
    # graph.tools is live. These two API-only helpers aren't part of contracts/tools.md's
    # 11 agent tools, so graph.tools doesn't define them - read directly via graph.db/
    # graph.evidence instead, reusing the same operational-node filtering and node/edge
    # rendering graph/tools.py's own queries rely on.
    def graph_neighborhood(
        focus: str | None = None, depth: int = 2, cap: int = 500, scope: str = "overview"
    ) -> dict:
        from graph.db import get_graph
        from graph.evidence import Evidence

        g = get_graph()
        evidence = Evidence()
        if focus is None and scope == "overview":
            # The legible default: just Service/DEPENDS_ON plus Team/OWNS->Service -
            # ~12-20 nodes for the demo dataset, not the whole graph. The (s:Service)
            # label constraint on OWNS keeps this from pulling in CODEOWNERS Team/
            # Person -> File ownership edges, which vastly outnumber Team -> Service.
            rows = g.query(
                "MATCH (s:Service) "
                "OPTIONAL MATCH dep=(s)-[:DEPENDS_ON]->(:Service) "
                "OPTIONAL MATCH own=(:Team)-[:OWNS]->(s) "
                "RETURN s, dep, own",
                {},
            ).result_set
            for s, dep, own in rows:
                evidence.add(s)
                if dep is not None:
                    evidence.add(dep)
                if own is not None:
                    evidence.add(own)
            return evidence.render()

        if focus is None:  # scope == "all"
            # cap bounds the rendered node count itself, not a seed set to expand from -
            # take the first `cap` nodes, then only edges strictly within that set.
            nodes = g.query(
                "MATCH (n) WHERE coalesce(n.operational, false) = false "
                "RETURN n ORDER BY n.id LIMIT $cap",
                {"cap": cap},
            ).result_set
            prop_ids = [n.properties["id"] for (n,) in nodes]
            for (n,) in nodes:
                evidence.add(n)
            edges = g.query(
                "MATCH (n)-[r]->(m) WHERE coalesce(r.operational, false) = false "
                "AND n.id IN $ids AND m.id IN $ids RETURN r",
                {"ids": prop_ids},
            ).result_set
            for (r,) in edges:
                evidence.add(r)
            return evidence.render()

        # Variable-length relationship bounds must be literal ints in Cypher, not params.
        safe_depth = max(0, min(depth, 4))
        rows = g.query(
            f"MATCH (focus {{id: $focus}}) "
            f"OPTIONAL MATCH path=(focus)-[*0..{safe_depth}]-(other) "
            "RETURN DISTINCT other, path LIMIT $cap",
            {"focus": focus, "cap": cap},
        ).result_set
        if not rows:
            raise ValueError(f"unknown node: {focus}")
        for _, path in rows:
            if path is not None:
                evidence.add(path)
        return evidence.render()

    def graph_stats() -> dict:
        from graph.db import get_graph

        g = get_graph()
        nodes_by_label = dict(
            g.query(
                "MATCH (n) WHERE coalesce(n.operational, false) = false "
                "RETURN labels(n)[0], count(n)",
                {},
            ).result_set
        )
        edges_by_type = dict(
            g.query(
                "MATCH ()-[r]->() WHERE coalesce(r.operational, false) = false "
                "RETURN type(r), count(r)",
                {},
            ).result_set
        )
        synthetic_count, real_count = g.query(
            "MATCH (n) WHERE coalesce(n.operational, false) = false "
            "RETURN sum(CASE WHEN n.synthetic THEN 1 ELSE 0 END), "
            "sum(CASE WHEN n.synthetic THEN 0 ELSE 1 END)",
            {},
        ).result_set[0]
        meta = g.query("MATCH (m:SyncMeta {id: 'meta:sync'}) RETURN m.last_synced_at", {}).result_set
        return {
            "nodes_by_label": nodes_by_label,
            "edges_by_type": edges_by_type,
            "synthetic_node_count": int(synthetic_count or 0),
            "real_node_count": int(real_count or 0),
            "last_synced_at": meta[0][0] if meta else None,
        }


TOOL_REGISTRY: dict[str, Callable[..., dict]] = {
    "search_entities": search_entities,
    "blast_radius": blast_radius,
    "failure_path": failure_path,
    "find_owners": find_owners,
    "find_experts": find_experts,
    "similar_incidents": similar_incidents,
    "trace_decision": trace_decision,
    "critical_services": critical_services,
    "single_points_of_failure": single_points_of_failure,
    "team_clusters": team_clusters,
    "create_incident_issue": create_incident_issue,
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_entities",
        "description": "Free-text search across node names/ids of any label (Service, Person, Team, Incident, Decision, ...).",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "search text"}},
            "required": ["text"],
        },
    },
    {
        "name": "blast_radius",
        "description": "Find everything that transitively depends on a service and therefore breaks if it goes down.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "service id (e.g. 'svc:cartservice') or bare name"},
                "max_depth": {"type": "integer", "description": "max hops to walk", "default": 4},
            },
            "required": ["service"],
        },
    },
    {
        "name": "failure_path",
        "description": "Shortest dependency path between two services, to explain how a failure in one reaches the other.",
        "parameters": {
            "type": "object",
            "properties": {
                "from_service": {"type": "string", "description": "service id or bare name"},
                "to_service": {"type": "string", "description": "service id or bare name"},
            },
            "required": ["from_service", "to_service"],
        },
    },
    {
        "name": "find_owners",
        "description": "Find the team and team members that own a service.",
        "parameters": {
            "type": "object",
            "properties": {"service": {"type": "string", "description": "service id or bare name"}},
            "required": ["service"],
        },
    },
    {
        "name": "find_experts",
        "description": "Find people who recently authored PRs touching a service's files, ranked by PR count.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "service id or bare name"},
                "days": {"type": "integer", "description": "lookback window in days", "default": 180},
            },
            "required": ["service"],
        },
    },
    {
        "name": "similar_incidents",
        "description": "Find past incidents that caused or affected this service or its direct dependency neighbors.",
        "parameters": {
            "type": "object",
            "properties": {"service": {"type": "string", "description": "service id or bare name"}},
            "required": ["service"],
        },
    },
    {
        "name": "trace_decision",
        "description": "Find architectural decisions (ADRs) that govern a service, and the PRs they cite.",
        "parameters": {
            "type": "object",
            "properties": {"service": {"type": "string", "description": "service id or bare name"}},
            "required": ["service"],
        },
    },
    {
        "name": "critical_services",
        "description": "Rank services by PageRank over the dependency graph to find the most structurally critical ones.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "single_points_of_failure",
        "description": "Rank services by betweenness centrality over the dependency graph to find single points of failure.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "team_clusters",
        "description": "Detect clusters of tightly-coupled services and label each cluster by its dominant owning team.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "create_incident_issue",
        "description": "Draft (dry_run=True, default) or file a GitHub issue summarizing an incident on a service, and record it in the graph.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "service id or bare name"},
                "summary": {"type": "string", "description": "incident summary / issue body"},
                "dry_run": {"type": "boolean", "description": "if true (default), draft without filing on GitHub", "default": True},
            },
            "required": ["service", "summary"],
        },
    },
]

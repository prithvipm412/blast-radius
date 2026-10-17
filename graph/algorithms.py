"""Native algorithms with explicit, narrowly triggered NetworkX compatibility fallback."""

from collections import Counter, defaultdict
from functools import lru_cache

from graph import queries as q
from graph.db import get_graph


@lru_cache(maxsize=8)
def _procedures(graph):
    return frozenset(row[0] for row in graph.query(q.PROCEDURES, {}).result_set)


def run_algorithm(kind, run, result, cap):
    graph = get_graph()
    names = {
        "pagerank": "algo.pageRank",
        "betweenness": "algo.betweenness",
        "clusters": "algo.labelPropagation",
    }
    queries = {"pagerank": q.PAGERANK, "betweenness": q.BETWEENNESS, "clusters": q.COMMUNITIES}
    params = {"limit": cap + 1}
    if names[kind] in _procedures(graph):
        query = queries[kind]
        if kind == "pagerank":
            params.update(label="Service", relationship="DEPENDS_ON")
        else:
            params["config"] = {"nodeLabels": ["Service"], "relationshipTypes": ["DEPENDS_ON"]}
            if kind == "betweenness":
                params["config"].update(samplingSize=cap, samplingSeed=42)
            else:
                params["config"]["maxIterations"] = 100
        rows, evidence = run(query, params)
        scores = {row[0].properties["id"]: row[1] for row in rows}
        method = None
    else:
        # Only absent procedures trigger fallback. Query/auth/connection failures raise.
        import networkx as nx

        query = q.CLUSTER_EXPORT if kind == "clusters" else q.SERVICES
        rows, evidence = run(query, params)
        projection = nx.DiGraph()
        projection.add_nodes_from(row[0].properties["id"] for row in rows)
        for edge in evidence.render()["edges"]:
            if edge["type"] == "DEPENDS_ON":
                projection.add_edge(edge["source"], edge["target"])
        if kind == "pagerank":
            scores = nx.pagerank(projection)
        elif kind == "betweenness":
            scores = nx.betweenness_centrality(projection, normalized=False)
        else:
            groups = nx.community.asyn_lpa_communities(projection.to_undirected(), seed=42)
            scores = {
                node: i for i, group in enumerate(sorted(map(sorted, groups))) for node in group
            }
        if kind == "pagerank":
            query = q.STORE_CRITICALITY
            params["scores"] = [
                {"id": node, "score": float(score)} for node, score in scores.items()
            ]
            _, evidence = run(query, params)
        method = "networkx-fallback"
    nodes = {node.properties["id"]: node.properties for node in evidence.nodes.values()}
    if kind == "clusters":
        groups = defaultdict(list)
        for node, community in scores.items():
            groups[community].append(node)
        owners = defaultdict(set)
        for edge in evidence.render()["edges"]:
            if edge["type"] == "OWNS":
                owners[edge["target"]].add(edge["source"])
        clusters = []
        for i, members in enumerate(sorted(sorted(m) for m in groups.values())):
            counts = Counter(team for member in members for team in owners[member])
            dominant = min(counts, key=lambda t: (-counts[t], t)) if counts else None
            clusters.append({"cluster_id": i, "services": members, "dominant_team": dominant})
        data = {"clusters": clusters}
    else:
        data = {
            "ranked": [
                {"id": id_, "name": nodes[id_]["name"], "score": float(score)}
                for id_, score in sorted(scores.items(), key=lambda x: (-x[1], x[0]))
            ]
        }
    if method:
        data["method"] = method
    return result(data, query, params, evidence)

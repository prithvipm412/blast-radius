"""Integration fixtures: every database operation targets blast_radius_test only."""

import json
from pathlib import Path

import pytest

from graph.db import get_graph

# Label/type syntax is fixed at source, never interpolated from fixture values.
NODE_QUERIES = {
    "Service": "UNWIND $nodes AS props CREATE (n:Service) SET n = props",
    "Person": "UNWIND $nodes AS props CREATE (n:Person) SET n = props",
    "Team": "UNWIND $nodes AS props CREATE (n:Team) SET n = props",
    "Repo": "UNWIND $nodes AS props CREATE (n:Repo) SET n = props",
    "File": "UNWIND $nodes AS props CREATE (n:File) SET n = props",
    "PR": "UNWIND $nodes AS props CREATE (n:PR) SET n = props",
    "Issue": "UNWIND $nodes AS props CREATE (n:Issue) SET n = props",
    "Incident": "UNWIND $nodes AS props CREATE (n:Incident) SET n = props",
    "Decision": "UNWIND $nodes AS props CREATE (n:Decision) SET n = props",
    "Doc": "UNWIND $nodes AS props CREATE (n:Doc) SET n = props",
}
EDGE_QUERIES = {
    "DEPENDS_ON": "UNWIND $edges AS e MATCH (a {id:e.source}), (b {id:e.target}) CREATE (a)-[r:DEPENDS_ON]->(b) SET r = e.props",
    "OWNS": "UNWIND $edges AS e MATCH (a {id:e.source}), (b {id:e.target}) CREATE (a)-[r:OWNS]->(b) SET r = e.props",
    "MEMBER_OF": "UNWIND $edges AS e MATCH (a {id:e.source}), (b {id:e.target}) CREATE (a)-[r:MEMBER_OF]->(b) SET r = e.props",
    "AUTHORED": "UNWIND $edges AS e MATCH (a {id:e.source}), (b {id:e.target}) CREATE (a)-[r:AUTHORED]->(b) SET r = e.props",
    "TOUCHED": "UNWIND $edges AS e MATCH (a {id:e.source}), (b {id:e.target}) CREATE (a)-[r:TOUCHED]->(b) SET r = e.props",
    "CONTAINS": "UNWIND $edges AS e MATCH (a {id:e.source}), (b {id:e.target}) CREATE (a)-[r:CONTAINS]->(b) SET r = e.props",
    "CAUSED": "UNWIND $edges AS e MATCH (a {id:e.source}), (b {id:e.target}) CREATE (a)-[r:CAUSED]->(b) SET r = e.props",
    "AFFECTED": "UNWIND $edges AS e MATCH (a {id:e.source}), (b {id:e.target}) CREATE (a)-[r:AFFECTED]->(b) SET r = e.props",
    "RESOLVED_BY": "UNWIND $edges AS e MATCH (a {id:e.source}), (b {id:e.target}) CREATE (a)-[r:RESOLVED_BY]->(b) SET r = e.props",
    "DECIDED": "UNWIND $edges AS e MATCH (a {id:e.source}), (b {id:e.target}) CREATE (a)-[r:DECIDED]->(b) SET r = e.props",
    "CITES": "UNWIND $edges AS e MATCH (a {id:e.source}), (b {id:e.target}) CREATE (a)-[r:CITES]->(b) SET r = e.props",
    "MENTIONS": "UNWIND $edges AS e MATCH (a {id:e.source}), (b {id:e.target}) CREATE (a)-[r:MENTIONS]->(b) SET r = e.props",
}


@pytest.fixture(scope="session")
def sample_graph():
    return json.loads((Path(__file__).parents[1] / "fixtures/sample_graph.json").read_text())


@pytest.fixture(scope="session")
def loaded_graph(sample_graph):
    graph = get_graph("blast_radius_test")
    assert graph.name == "blast_radius_test"
    graph.query("MATCH (n) DETACH DELETE n", {})
    for label, query in NODE_QUERIES.items():
        nodes = [{k: v for k, v in n.items() if k != "label"}
                 for n in sample_graph["nodes"] if n["label"] == label]
        graph.query(query, {"nodes": nodes})
    for relation, query in EDGE_QUERIES.items():
        edges = [{"source": e["source"], "target": e["target"],
                  "props": {k: v for k, v in e.items() if k not in ("source", "target", "type")}}
                 for e in sample_graph["edges"] if e["type"] == relation]
        graph.query(query, {"edges": edges})
    yield graph
    assert graph.name == "blast_radius_test"
    graph.query("MATCH (n) DETACH DELETE n", {})


@pytest.fixture
def graph(loaded_graph, monkeypatch):
    monkeypatch.setenv("FALKORDB_GRAPH", "blast_radius_test")
    return loaded_graph

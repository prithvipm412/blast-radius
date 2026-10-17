"""Literal parameterized queries. Caps fail closed rather than silently truncate evidence."""

SEARCH = """MATCH (n)
WHERE toLower(n.name) CONTAINS $text OR toLower(n.id) CONTAINS $text
RETURN n ORDER BY n.id LIMIT $limit"""

BLAST = """MATCH (s:Service {id: $service})
OPTIONAL MATCH (a:Service)
WHERE a.id <> s.id
WITH s, a, shortestPath((s)<-[:DEPENDS_ON*]-(a)) AS p
RETURN s, CASE WHEN length(p) <= $max_depth THEN p ELSE null END,
CASE WHEN length(p) <= $max_depth THEN a ELSE null END
LIMIT $limit"""

EXPERTS = """MATCH (s:Service {id: $service})
OPTIONAL MATCH p=(s)-[:CONTAINS]->(f:File)<-[:TOUCHED]-(pr:PR)<-[:AUTHORED]-(person:Person)
WHERE pr.merged_at >= $cutoff AND pr.merged_at <= $now
RETURN s, p ORDER BY pr.merged_at DESC, person.id, pr.id LIMIT $limit"""

INCIDENTS = """MATCH (s:Service {id: $service})
OPTIONAL MATCH neighborhood=(s)-[:DEPENDS_ON*0..1]-(near:Service)
OPTIONAL MATCH evidence=(i:Incident)-[:CAUSED|AFFECTED]->(near)
RETURN s, neighborhood, evidence ORDER BY i.started_at DESC, i.id LIMIT $limit"""

DECISIONS = """MATCH (s:Service {id: $service})
OPTIONAL MATCH decision=(d:Decision)-[:DECIDED]->(s)
OPTIONAL MATCH citation=(d)-[:CITES]->(pr:PR)
OPTIONAL MATCH context=(i:Incident)-[:CITES]->(d)
RETURN s, decision, citation, context ORDER BY d.decided_at DESC, d.id LIMIT $limit"""

SERVICES = """MATCH (s:Service)
OPTIONAL MATCH p=(s)-[:DEPENDS_ON]->(t:Service)
RETURN s, p ORDER BY s.id, t.id LIMIT $limit"""

TEAMS = """MATCH p=(t:Team)-[:OWNS]->(s:Service)
RETURN p ORDER BY t.id, s.id LIMIT $limit"""

PAGERANK = """CALL algo.pageRank($label, $relationship)
YIELD node, score
OPTIONAL MATCH p=(node)-[:DEPENDS_ON]->(:Service)
RETURN node, score, p ORDER BY score DESC, node.id LIMIT $limit"""
BETWEENNESS = """CALL algo.betweenness($config)
YIELD node, score
OPTIONAL MATCH p=(node)-[:DEPENDS_ON]->(:Service)
RETURN node, score, p ORDER BY score DESC, node.id LIMIT $limit"""
COMMUNITIES = """CALL algo.labelPropagation($config)
YIELD node, communityId
OPTIONAL MATCH p=(node)-[:DEPENDS_ON]->(:Service)
OPTIONAL MATCH ownership=(t:Team)-[:OWNS]->(node)
RETURN node, communityId, p, ownership ORDER BY node.id LIMIT $limit"""
PROCEDURES = "CALL dbms.procedures() YIELD name RETURN name"

CLUSTER_EXPORT = """MATCH (s:Service)
OPTIONAL MATCH p=(s)-[:DEPENDS_ON]->(t:Service)
OPTIONAL MATCH ownership=(:Team)-[:OWNS]->(s)
RETURN s, p, ownership ORDER BY s.id LIMIT $limit"""

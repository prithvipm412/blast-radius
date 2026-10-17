# Graph query reference

All runtime values are passed as parameters. Tool queries cap evidence at 2,000 rows (overflow raises); search returns at most 50 matches. Tests use only `blast_radius_test`.

Native algorithms: [PageRank](https://docs.falkordb.com/algorithms/pagerank), [betweenness](https://docs.falkordb.com/algorithms/betweenness-centrality), and [label propagation](https://docs.falkordb.com/algorithms/cdlp). Procedures are checked via `dbms.procedures`; missing procedures alone trigger NetworkX fallback (`data.method="networkx-fallback"`). PageRank stores `Service.criticality`; betweenness is unnormalized; fallback communities use seeded asynchronous label propagation.

Incident reports use the investigation queries plus SOURCES, then ISSUE. Their envelope reports the final write and its exact parameters; path includes the combined investigation and write evidence. GitHub filing requires GITHUB_ISSUE_REPO and rejects the upstream repository.

Pending contract clarification: multiple owning teams; failure_path when only an undirected path exists. These cases raise NotImplementedError. Draft body and fallback method fields follow the explicit task instructions.

## SEARCH

Case-insensitive entity search excluding operational metadata.

```cypher
MATCH (n)
WHERE coalesce(n.operational, false) = false
AND (toLower(n.name) CONTAINS $text OR toLower(n.id) CONTAINS $text)
RETURN n ORDER BY n.id LIMIT $limit
```

## BLAST

Incoming variable-length shortest dependency paths, filtered by max_depth.

```cypher
MATCH (s:Service {id: $service})
OPTIONAL MATCH (a:Service)
WHERE a.id <> s.id
WITH s, a, shortestPath((s)<-[:DEPENDS_ON*]-(a)) AS p
RETURN s, CASE WHEN length(p) <= $max_depth THEN p ELSE null END,
CASE WHEN length(p) <= $max_depth THEN a ELSE null END
LIMIT $limit
```

## EXPERTS

Recent merged PR authors connected through service files.

```cypher
MATCH (s:Service {id: $service})
OPTIONAL MATCH p=(s)-[:CONTAINS]->(f:File)<-[:TOUCHED]-(pr:PR)<-[:AUTHORED]-(person:Person)
WHERE pr.merged_at >= $cutoff AND pr.merged_at <= $now
RETURN s, p ORDER BY pr.merged_at DESC, person.id, pr.id LIMIT $limit
```

## INCIDENTS

Incidents affecting this service or a one-hop dependency neighbor.

```cypher
MATCH (s:Service {id: $service})
OPTIONAL MATCH neighborhood=(s)-[:DEPENDS_ON*0..1]-(near:Service)
OPTIONAL MATCH evidence=(i:Incident)-[:CAUSED|AFFECTED]->(near)
RETURN s, neighborhood, evidence ORDER BY i.started_at DESC, i.id LIMIT $limit
```

## DECISIONS

Decisions, cited PRs, and citing incidents.

```cypher
MATCH (s:Service {id: $service})
OPTIONAL MATCH decision=(d:Decision)-[:DECIDED]->(s)
OPTIONAL MATCH citation=(d)-[:CITES]->(pr:PR)
OPTIONAL MATCH context=(i:Incident)-[:CITES]->(d)
RETURN s, decision, citation, context ORDER BY d.decided_at DESC, d.id LIMIT $limit
```

## SERVICES

Export the dependency subgraph for unavailable native algorithms.

```cypher
MATCH (s:Service)
OPTIONAL MATCH p=(s)-[:DEPENDS_ON]->(t:Service)
RETURN s, p ORDER BY s.id, t.id LIMIT $limit
```

## TEAMS

Export ownership edges.

```cypher
MATCH p=(t:Team)-[:OWNS]->(s:Service)
RETURN p ORDER BY t.id, s.id LIMIT $limit
```

## PAGERANK

Native PageRank and dependency evidence, storing criticality.

```cypher
CALL algo.pageRank($label, $relationship)
YIELD node, score
SET node.criticality = score
WITH node, score
OPTIONAL MATCH p=(node)-[:DEPENDS_ON]->(:Service)
RETURN node, score, p ORDER BY score DESC, node.id LIMIT $limit
```

## BETWEENNESS

Native betweenness and dependency evidence.

```cypher
CALL algo.betweenness($config)
YIELD node, score
OPTIONAL MATCH p=(node)-[:DEPENDS_ON]->(:Service)
RETURN node, score, p ORDER BY score DESC, node.id LIMIT $limit
```

## COMMUNITIES

Native label propagation with ownership evidence.

```cypher
CALL algo.labelPropagation($config)
YIELD node, communityId
OPTIONAL MATCH p=(node)-[:DEPENDS_ON]->(:Service)
OPTIONAL MATCH ownership=(t:Team)-[:OWNS]->(node)
RETURN node, communityId, p, ownership ORDER BY node.id LIMIT $limit
```

## PROCEDURES

Detect native procedure availability.

```cypher
CALL dbms.procedures() YIELD name RETURN name
```

## CLUSTER_EXPORT

Export dependencies and ownership for community fallback.

```cypher
MATCH (s:Service)
OPTIONAL MATCH p=(s)-[:DEPENDS_ON]->(t:Service)
OPTIONAL MATCH ownership=(:Team)-[:OWNS]->(s)
RETURN s, p, ownership ORDER BY s.id LIMIT $limit
```

## OWNERS

Owning teams and their members.

```cypher
MATCH (s:Service {id: $service})
OPTIONAL MATCH ownership=(t:Team)-[:OWNS]->(s)
OPTIONAL MATCH membership=(person:Person)-[:MEMBER_OF]->(t)
RETURN s, ownership, membership ORDER BY t.id, person.id LIMIT $limit
```

## FAILURE

Incoming failure path plus connectivity check for unresolved direction cases.

```cypher
OPTIONAL MATCH (a:Service {id: $from_service})
OPTIONAL MATCH (b:Service {id: $to_service})
WITH a, b, shortestPath((a)<-[:DEPENDS_ON*]-(b)) AS p
OPTIONAL MATCH connected=(a)-[:DEPENDS_ON*]-(b)
RETURN a, b, p, length(connected) LIMIT $limit
```

## ISSUE

Record synthetic incident, issue, and CAUSED evidence.

```cypher
MATCH (s:Service {id: $service})
CREATE (i:Incident) SET i = $incident
CREATE (issue:Issue) SET issue = $issue
CREATE (i)-[e:CAUSED {synthetic: $synthetic, source_url: $source_url}]->(s)
RETURN i, e, s, issue
```

## SOURCES

Retrieve citation properties for incident drafting.

```cypher
MATCH (n) WHERE n.id IN $ids RETURN n ORDER BY n.id LIMIT $limit
```

## STORE_CRITICALITY

Persist fallback PageRank scores with dependency evidence.

```cypher
UNWIND $scores AS item
MATCH (s:Service {id: item.id}) SET s.criticality = item.score
WITH s OPTIONAL MATCH p=(s)-[:DEPENDS_ON]->(:Service)
RETURN s, p LIMIT $limit
```

## Schema startup

Check existing indexes and constraints before creating missing ones; wait for uniqueness constraints to become operational.

```cypher
CALL db.indexes() YIELD label, properties RETURN label, properties
CALL db.constraints()
CREATE INDEX FOR (n:Commit) ON (n.id)
CREATE INDEX FOR (n:SyncMeta) ON (n.id)
CREATE INDEX FOR (n:Commit) ON (n.sha)
CREATE INDEX FOR (n:Service) ON (n.id)
CREATE INDEX FOR (n:Person) ON (n.id)
CREATE INDEX FOR (n:Team) ON (n.id)
CREATE INDEX FOR (n:Repo) ON (n.id)
CREATE INDEX FOR (n:File) ON (n.id)
CREATE INDEX FOR (n:PR) ON (n.id)
CREATE INDEX FOR (n:Issue) ON (n.id)
CREATE INDEX FOR (n:Incident) ON (n.id)
CREATE INDEX FOR (n:Decision) ON (n.id)
CREATE INDEX FOR (n:Doc) ON (n.id)
CREATE INDEX FOR (n:Service) ON (n.name)
CREATE INDEX FOR (n:Person) ON (n.github_login)
```

Uniqueness uses the native Redis command `GRAPH.CONSTRAINT CREATE <graph> UNIQUE NODE <label> PROPERTIES 1 id`, with arguments passed separately, for each indexed id label.

## Node upserts

Static query selection by schema label/type; all record properties and custom keys are parameters. MERGE prevents duplicate entities. Edge batches validate all endpoints and provenance before writing.

### Service

```cypher
UNWIND $records AS record
MERGE (n:Service {id: record.id}) SET n += record
RETURN count(n)
```

### Person

```cypher
UNWIND $records AS record
MERGE (n:Person {id: record.id}) SET n += record
RETURN count(n)
```

### Team

```cypher
UNWIND $records AS record
MERGE (n:Team {id: record.id}) SET n += record
RETURN count(n)
```

### Repo

```cypher
UNWIND $records AS record
MERGE (n:Repo {id: record.id}) SET n += record
RETURN count(n)
```

### File

```cypher
UNWIND $records AS record
MERGE (n:File {id: record.id}) SET n += record
RETURN count(n)
```

### Commit

```cypher
UNWIND $records AS record
MERGE (n:Commit {id: record.id}) SET n += record
RETURN count(n)
```

### PR

```cypher
UNWIND $records AS record
MERGE (n:PR {id: record.id}) SET n += record
RETURN count(n)
```

### Issue

```cypher
UNWIND $records AS record
MERGE (n:Issue {id: record.id}) SET n += record
RETURN count(n)
```

### Incident

```cypher
UNWIND $records AS record
MERGE (n:Incident {id: record.id}) SET n += record
RETURN count(n)
```

### Decision

```cypher
UNWIND $records AS record
MERGE (n:Decision {id: record.id}) SET n += record
RETURN count(n)
```

### Doc

```cypher
UNWIND $records AS record
MERGE (n:Doc {id: record.id}) SET n += record
RETURN count(n)
```

### SyncMeta

```cypher
UNWIND $records AS record
MERGE (n:SyncMeta {id: record.id}) SET n += record
RETURN count(n)
```

## Custom-key node upserts

Static query selection by schema label/type; all record properties and custom keys are parameters. MERGE prevents duplicate entities. Edge batches validate all endpoints and provenance before writing.

### Service

```cypher
UNWIND $records AS record
OPTIONAL MATCH (existing:Service) WHERE existing[$key] = record[$key]
WITH record, coalesce(existing.id, record.id) AS identity
MERGE (n:Service {id: identity}) SET n += record
RETURN count(n)
```

### Person

```cypher
UNWIND $records AS record
OPTIONAL MATCH (existing:Person) WHERE existing[$key] = record[$key]
WITH record, coalesce(existing.id, record.id) AS identity
MERGE (n:Person {id: identity}) SET n += record
RETURN count(n)
```

### Team

```cypher
UNWIND $records AS record
OPTIONAL MATCH (existing:Team) WHERE existing[$key] = record[$key]
WITH record, coalesce(existing.id, record.id) AS identity
MERGE (n:Team {id: identity}) SET n += record
RETURN count(n)
```

### Repo

```cypher
UNWIND $records AS record
OPTIONAL MATCH (existing:Repo) WHERE existing[$key] = record[$key]
WITH record, coalesce(existing.id, record.id) AS identity
MERGE (n:Repo {id: identity}) SET n += record
RETURN count(n)
```

### File

```cypher
UNWIND $records AS record
OPTIONAL MATCH (existing:File) WHERE existing[$key] = record[$key]
WITH record, coalesce(existing.id, record.id) AS identity
MERGE (n:File {id: identity}) SET n += record
RETURN count(n)
```

### Commit

```cypher
UNWIND $records AS record
OPTIONAL MATCH (existing:Commit) WHERE existing[$key] = record[$key]
WITH record, coalesce(existing.id, record.id) AS identity
MERGE (n:Commit {id: identity}) SET n += record
RETURN count(n)
```

### PR

```cypher
UNWIND $records AS record
OPTIONAL MATCH (existing:PR) WHERE existing[$key] = record[$key]
WITH record, coalesce(existing.id, record.id) AS identity
MERGE (n:PR {id: identity}) SET n += record
RETURN count(n)
```

### Issue

```cypher
UNWIND $records AS record
OPTIONAL MATCH (existing:Issue) WHERE existing[$key] = record[$key]
WITH record, coalesce(existing.id, record.id) AS identity
MERGE (n:Issue {id: identity}) SET n += record
RETURN count(n)
```

### Incident

```cypher
UNWIND $records AS record
OPTIONAL MATCH (existing:Incident) WHERE existing[$key] = record[$key]
WITH record, coalesce(existing.id, record.id) AS identity
MERGE (n:Incident {id: identity}) SET n += record
RETURN count(n)
```

### Decision

```cypher
UNWIND $records AS record
OPTIONAL MATCH (existing:Decision) WHERE existing[$key] = record[$key]
WITH record, coalesce(existing.id, record.id) AS identity
MERGE (n:Decision {id: identity}) SET n += record
RETURN count(n)
```

### Doc

```cypher
UNWIND $records AS record
OPTIONAL MATCH (existing:Doc) WHERE existing[$key] = record[$key]
WITH record, coalesce(existing.id, record.id) AS identity
MERGE (n:Doc {id: identity}) SET n += record
RETURN count(n)
```

### SyncMeta

```cypher
UNWIND $records AS record
OPTIONAL MATCH (existing:SyncMeta) WHERE existing[$key] = record[$key]
WITH record, coalesce(existing.id, record.id) AS identity
MERGE (n:SyncMeta {id: identity}) SET n += record
RETURN count(n)
```

## Edge upserts

Static query selection by schema label/type; all record properties and custom keys are parameters. MERGE prevents duplicate entities. Edge batches validate all endpoints and provenance before writing.

### ('DEPENDS_ON', 'Service', 'Service')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Service {id: record.from_id})
OPTIONAL MATCH (b:Service {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:DEPENDS_ON]->(b) SET r += record.props
RETURN count(r)
```

### ('OWNS', 'Team', 'Service')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Team {id: record.from_id})
OPTIONAL MATCH (b:Service {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:OWNS]->(b) SET r += record.props
RETURN count(r)
```

### ('OWNS', 'Team', 'File')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Team {id: record.from_id})
OPTIONAL MATCH (b:File {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:OWNS]->(b) SET r += record.props
RETURN count(r)
```

### ('OWNS', 'Person', 'File')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Person {id: record.from_id})
OPTIONAL MATCH (b:File {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:OWNS]->(b) SET r += record.props
RETURN count(r)
```

### ('MEMBER_OF', 'Person', 'Team')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Person {id: record.from_id})
OPTIONAL MATCH (b:Team {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true AND record.props.synthetic = b.synthetic)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:MEMBER_OF]->(b) SET r += record.props
RETURN count(r)
```

### ('AUTHORED', 'Person', 'PR')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Person {id: record.from_id})
OPTIONAL MATCH (b:PR {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:AUTHORED]->(b) SET r += record.props
RETURN count(r)
```

### ('AUTHORED', 'Person', 'Issue')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Person {id: record.from_id})
OPTIONAL MATCH (b:Issue {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:AUTHORED]->(b) SET r += record.props
RETURN count(r)
```

### ('AUTHORED', 'Person', 'Commit')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Person {id: record.from_id})
OPTIONAL MATCH (b:Commit {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:AUTHORED]->(b) SET r += record.props
RETURN count(r)
```

### ('TOUCHED', 'PR', 'File')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:PR {id: record.from_id})
OPTIONAL MATCH (b:File {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:TOUCHED]->(b) SET r += record.props
RETURN count(r)
```

### ('TOUCHED', 'Commit', 'File')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Commit {id: record.from_id})
OPTIONAL MATCH (b:File {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:TOUCHED]->(b) SET r += record.props
RETURN count(r)
```

### ('CONTAINS', 'Repo', 'File')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Repo {id: record.from_id})
OPTIONAL MATCH (b:File {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:CONTAINS]->(b) SET r += record.props
RETURN count(r)
```

### ('CONTAINS', 'Service', 'File')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Service {id: record.from_id})
OPTIONAL MATCH (b:File {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:CONTAINS]->(b) SET r += record.props
RETURN count(r)
```

### ('CAUSED', 'Incident', 'Service')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Incident {id: record.from_id})
OPTIONAL MATCH (b:Service {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:CAUSED]->(b) SET r += record.props
RETURN count(r)
```

### ('CAUSED', 'Incident', 'PR')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Incident {id: record.from_id})
OPTIONAL MATCH (b:PR {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:CAUSED]->(b) SET r += record.props
RETURN count(r)
```

### ('AFFECTED', 'Incident', 'Service')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Incident {id: record.from_id})
OPTIONAL MATCH (b:Service {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:AFFECTED]->(b) SET r += record.props
RETURN count(r)
```

### ('RESOLVED_BY', 'Incident', 'PR')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Incident {id: record.from_id})
OPTIONAL MATCH (b:PR {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:RESOLVED_BY]->(b) SET r += record.props
RETURN count(r)
```

### ('RESOLVED_BY', 'Issue', 'PR')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Issue {id: record.from_id})
OPTIONAL MATCH (b:PR {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:RESOLVED_BY]->(b) SET r += record.props
RETURN count(r)
```

### ('DECIDED', 'Decision', 'Service')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Decision {id: record.from_id})
OPTIONAL MATCH (b:Service {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:DECIDED]->(b) SET r += record.props
RETURN count(r)
```

### ('CITES', 'Decision', 'PR')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Decision {id: record.from_id})
OPTIONAL MATCH (b:PR {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:CITES]->(b) SET r += record.props
RETURN count(r)
```

### ('CITES', 'Decision', 'Doc')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Decision {id: record.from_id})
OPTIONAL MATCH (b:Doc {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:CITES]->(b) SET r += record.props
RETURN count(r)
```

### ('CITES', 'Incident', 'Decision')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Incident {id: record.from_id})
OPTIONAL MATCH (b:Decision {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:CITES]->(b) SET r += record.props
RETURN count(r)
```

### ('MENTIONS', 'Issue', 'Service')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Issue {id: record.from_id})
OPTIONAL MATCH (b:Service {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:MENTIONS]->(b) SET r += record.props
RETURN count(r)
```

### ('MENTIONS', 'Doc', 'Service')

```cypher
UNWIND $records AS record
OPTIONAL MATCH (a:Doc {id: record.from_id})
OPTIONAL MATCH (b:Service {id: record.to_id})
WITH collect({a:a, b:b, record:record}) AS batch
WHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
WITH collect({a:a, b:b, record:record, valid: (true AND record.props.synthetic = a.synthetic)}) AS batch
WHERE all(item IN batch WHERE item.valid)
UNWIND batch AS item
WITH item.a AS a, item.b AS b, item.record AS record
MERGE (a)-[r:MENTIONS]->(b) SET r += record.props
RETURN count(r)
```

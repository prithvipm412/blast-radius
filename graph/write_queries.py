"""Static, parameterized bulk-write queries for the contract labels and edge pairs."""

NODE_QUERIES = {
    "Service": "UNWIND $records AS record\nMERGE (n:Service {id: record.id}) SET n += record\nRETURN count(n)",
    "Person": "UNWIND $records AS record\nMERGE (n:Person {id: record.id}) SET n += record\nRETURN count(n)",
    "Team": "UNWIND $records AS record\nMERGE (n:Team {id: record.id}) SET n += record\nRETURN count(n)",
    "Repo": "UNWIND $records AS record\nMERGE (n:Repo {id: record.id}) SET n += record\nRETURN count(n)",
    "File": "UNWIND $records AS record\nMERGE (n:File {id: record.id}) SET n += record\nRETURN count(n)",
    "Commit": "UNWIND $records AS record\nMERGE (n:Commit {id: record.id}) SET n += record\nRETURN count(n)",
    "PR": "UNWIND $records AS record\nMERGE (n:PR {id: record.id}) SET n += record\nRETURN count(n)",
    "Issue": "UNWIND $records AS record\nMERGE (n:Issue {id: record.id}) SET n += record\nRETURN count(n)",
    "Incident": "UNWIND $records AS record\nMERGE (n:Incident {id: record.id}) SET n += record\nRETURN count(n)",
    "Decision": "UNWIND $records AS record\nMERGE (n:Decision {id: record.id}) SET n += record\nRETURN count(n)",
    "Doc": "UNWIND $records AS record\nMERGE (n:Doc {id: record.id}) SET n += record\nRETURN count(n)",
    "SyncMeta": "UNWIND $records AS record\nMERGE (n:SyncMeta {id: record.id}) SET n += record\nRETURN count(n)",
}

KEYED_NODE_QUERIES = {
    "Service": "UNWIND $records AS record\nOPTIONAL MATCH (existing:Service) WHERE existing[$key] = record[$key]\nWITH record, coalesce(existing.id, record.id) AS identity\nMERGE (n:Service {id: identity}) SET n += record\nRETURN count(n)",
    "Person": "UNWIND $records AS record\nOPTIONAL MATCH (existing:Person) WHERE existing[$key] = record[$key]\nWITH record, coalesce(existing.id, record.id) AS identity\nMERGE (n:Person {id: identity}) SET n += record\nRETURN count(n)",
    "Team": "UNWIND $records AS record\nOPTIONAL MATCH (existing:Team) WHERE existing[$key] = record[$key]\nWITH record, coalesce(existing.id, record.id) AS identity\nMERGE (n:Team {id: identity}) SET n += record\nRETURN count(n)",
    "Repo": "UNWIND $records AS record\nOPTIONAL MATCH (existing:Repo) WHERE existing[$key] = record[$key]\nWITH record, coalesce(existing.id, record.id) AS identity\nMERGE (n:Repo {id: identity}) SET n += record\nRETURN count(n)",
    "File": "UNWIND $records AS record\nOPTIONAL MATCH (existing:File) WHERE existing[$key] = record[$key]\nWITH record, coalesce(existing.id, record.id) AS identity\nMERGE (n:File {id: identity}) SET n += record\nRETURN count(n)",
    "Commit": "UNWIND $records AS record\nOPTIONAL MATCH (existing:Commit) WHERE existing[$key] = record[$key]\nWITH record, coalesce(existing.id, record.id) AS identity\nMERGE (n:Commit {id: identity}) SET n += record\nRETURN count(n)",
    "PR": "UNWIND $records AS record\nOPTIONAL MATCH (existing:PR) WHERE existing[$key] = record[$key]\nWITH record, coalesce(existing.id, record.id) AS identity\nMERGE (n:PR {id: identity}) SET n += record\nRETURN count(n)",
    "Issue": "UNWIND $records AS record\nOPTIONAL MATCH (existing:Issue) WHERE existing[$key] = record[$key]\nWITH record, coalesce(existing.id, record.id) AS identity\nMERGE (n:Issue {id: identity}) SET n += record\nRETURN count(n)",
    "Incident": "UNWIND $records AS record\nOPTIONAL MATCH (existing:Incident) WHERE existing[$key] = record[$key]\nWITH record, coalesce(existing.id, record.id) AS identity\nMERGE (n:Incident {id: identity}) SET n += record\nRETURN count(n)",
    "Decision": "UNWIND $records AS record\nOPTIONAL MATCH (existing:Decision) WHERE existing[$key] = record[$key]\nWITH record, coalesce(existing.id, record.id) AS identity\nMERGE (n:Decision {id: identity}) SET n += record\nRETURN count(n)",
    "Doc": "UNWIND $records AS record\nOPTIONAL MATCH (existing:Doc) WHERE existing[$key] = record[$key]\nWITH record, coalesce(existing.id, record.id) AS identity\nMERGE (n:Doc {id: identity}) SET n += record\nRETURN count(n)",
    "SyncMeta": "UNWIND $records AS record\nOPTIONAL MATCH (existing:SyncMeta) WHERE existing[$key] = record[$key]\nWITH record, coalesce(existing.id, record.id) AS identity\nMERGE (n:SyncMeta {id: identity}) SET n += record\nRETURN count(n)",
}

EDGE_QUERIES = {
    (
        "DEPENDS_ON",
        "Service",
        "Service",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Service {id: record.from_id})\nOPTIONAL MATCH (b:Service {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:DEPENDS_ON]->(b) SET r += record.props\nRETURN count(r)",
    (
        "OWNS",
        "Team",
        "Service",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Team {id: record.from_id})\nOPTIONAL MATCH (b:Service {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:OWNS]->(b) SET r += record.props\nRETURN count(r)",
    (
        "OWNS",
        "Team",
        "File",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Team {id: record.from_id})\nOPTIONAL MATCH (b:File {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:OWNS]->(b) SET r += record.props\nRETURN count(r)",
    (
        "OWNS",
        "Person",
        "File",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Person {id: record.from_id})\nOPTIONAL MATCH (b:File {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:OWNS]->(b) SET r += record.props\nRETURN count(r)",
    (
        "MEMBER_OF",
        "Person",
        "Team",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Person {id: record.from_id})\nOPTIONAL MATCH (b:Team {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true AND record.props.synthetic = b.synthetic)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:MEMBER_OF]->(b) SET r += record.props\nRETURN count(r)",
    (
        "AUTHORED",
        "Person",
        "PR",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Person {id: record.from_id})\nOPTIONAL MATCH (b:PR {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:AUTHORED]->(b) SET r += record.props\nRETURN count(r)",
    (
        "AUTHORED",
        "Person",
        "Issue",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Person {id: record.from_id})\nOPTIONAL MATCH (b:Issue {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:AUTHORED]->(b) SET r += record.props\nRETURN count(r)",
    (
        "AUTHORED",
        "Person",
        "Commit",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Person {id: record.from_id})\nOPTIONAL MATCH (b:Commit {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:AUTHORED]->(b) SET r += record.props\nRETURN count(r)",
    (
        "TOUCHED",
        "PR",
        "File",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:PR {id: record.from_id})\nOPTIONAL MATCH (b:File {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:TOUCHED]->(b) SET r += record.props\nRETURN count(r)",
    (
        "TOUCHED",
        "Commit",
        "File",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Commit {id: record.from_id})\nOPTIONAL MATCH (b:File {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:TOUCHED]->(b) SET r += record.props\nRETURN count(r)",
    (
        "CONTAINS",
        "Repo",
        "File",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Repo {id: record.from_id})\nOPTIONAL MATCH (b:File {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:CONTAINS]->(b) SET r += record.props\nRETURN count(r)",
    (
        "CONTAINS",
        "Service",
        "File",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Service {id: record.from_id})\nOPTIONAL MATCH (b:File {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:CONTAINS]->(b) SET r += record.props\nRETURN count(r)",
    (
        "CAUSED",
        "Incident",
        "Service",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Incident {id: record.from_id})\nOPTIONAL MATCH (b:Service {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:CAUSED]->(b) SET r += record.props\nRETURN count(r)",
    (
        "CAUSED",
        "Incident",
        "PR",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Incident {id: record.from_id})\nOPTIONAL MATCH (b:PR {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:CAUSED]->(b) SET r += record.props\nRETURN count(r)",
    (
        "AFFECTED",
        "Incident",
        "Service",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Incident {id: record.from_id})\nOPTIONAL MATCH (b:Service {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:AFFECTED]->(b) SET r += record.props\nRETURN count(r)",
    (
        "RESOLVED_BY",
        "Incident",
        "PR",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Incident {id: record.from_id})\nOPTIONAL MATCH (b:PR {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:RESOLVED_BY]->(b) SET r += record.props\nRETURN count(r)",
    (
        "RESOLVED_BY",
        "Issue",
        "PR",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Issue {id: record.from_id})\nOPTIONAL MATCH (b:PR {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:RESOLVED_BY]->(b) SET r += record.props\nRETURN count(r)",
    (
        "DECIDED",
        "Decision",
        "Service",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Decision {id: record.from_id})\nOPTIONAL MATCH (b:Service {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:DECIDED]->(b) SET r += record.props\nRETURN count(r)",
    (
        "CITES",
        "Decision",
        "PR",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Decision {id: record.from_id})\nOPTIONAL MATCH (b:PR {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:CITES]->(b) SET r += record.props\nRETURN count(r)",
    (
        "CITES",
        "Decision",
        "Doc",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Decision {id: record.from_id})\nOPTIONAL MATCH (b:Doc {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:CITES]->(b) SET r += record.props\nRETURN count(r)",
    (
        "CITES",
        "Incident",
        "Decision",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Incident {id: record.from_id})\nOPTIONAL MATCH (b:Decision {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:CITES]->(b) SET r += record.props\nRETURN count(r)",
    (
        "MENTIONS",
        "Issue",
        "Service",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Issue {id: record.from_id})\nOPTIONAL MATCH (b:Service {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:MENTIONS]->(b) SET r += record.props\nRETURN count(r)",
    (
        "MENTIONS",
        "Doc",
        "Service",
    ): "UNWIND $records AS record\nOPTIONAL MATCH (a:Doc {id: record.from_id})\nOPTIONAL MATCH (b:Service {id: record.to_id})\nWITH collect({a:a, b:b, record:record}) AS batch\nWHERE all(item IN batch WHERE item.a IS NOT NULL AND item.b IS NOT NULL)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nWITH collect({a:a, b:b, record:record, valid: (true AND record.props.synthetic = a.synthetic)}) AS batch\nWHERE all(item IN batch WHERE item.valid)\nUNWIND batch AS item\nWITH item.a AS a, item.b AS b, item.record AS record\nMERGE (a)-[r:MENTIONS]->(b) SET r += record.props\nRETURN count(r)",
}

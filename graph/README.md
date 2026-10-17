# graph/ — owner: Codex 2

Read `contracts/schema.md` and `contracts/tools.md` first.

## Scope

- FalkorDB client setup (connection from `.env`, graph name `blast_radius`).
- All Cypher lives here. No other folder writes raw Cypher.
- `graph/tools.py` — the only import surface other folders use. Implements every function in `contracts/tools.md` with the exact signatures and return envelope (`{"data", "cypher", "params", "path"}`).
- Graph algorithms: `critical_services()` (PageRank), `single_points_of_failure()` (betweenness centrality), `team_clusters()` (community detection) — prefer FalkorDB's built-in graph algorithm procedures; fall back to a documented Cypher approximation only if the installed version lacks one.
- Index/constraint setup from `contracts/schema.md`'s DDL section, run idempotently at startup.
- (Stretch) an MCP server exposing these tools, if time allows — mentioned in the original brief; not required for the hackathon demo path, which goes through `agent/` + `api/` directly.

## Suggested layout

```
graph/
  __init__.py
  client.py       # FalkorDB connection, graph handle, index/constraint setup
  tools.py        # the contract surface — one function per contracts/tools.md entry
  queries.py      # Cypher string builders / helpers used by tools.py
  algorithms.py   # pagerank / betweenness / community detection wrappers
  mcp_server.py   # optional, stretch
```

## Hard rules (see AGENTS.md)

- Parameterized Cypher only — `$param`, never f-string interpolation.
- Don't change function signatures in `contracts/tools.md` without asking the human to relay it to the lead.
- Unknown entity lookups raise `ValueError`, don't return `None` silently.

## Getting started

1. `cp .env.example .env` and fill in `FALKORDB_*` (ask the lead/human for dev credentials if you don't have a local FalkorDB).
2. `python scripts/check_db.py` should print `OK`.
3. Develop against `tests/fixtures/sample_graph.json` (~15 nodes matching the schema) before real ingested data exists — load it into your local FalkorDB graph to iterate on Cypher/tools without waiting on `ingest/`.

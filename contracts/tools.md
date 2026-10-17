# Graph Tools Contract

Owner: **lead only** for this file. `graph/` (Codex 2) implements every function below with these exact signatures. `agent/` (lead) wires them up as LLM function-calling tools. `api/` (lead) exposes them over HTTP/SSE. `web/` (Codex 3) renders `path` from any tool result to highlight the graph.

## Universal return shape

**Every** tool function returns a dict with this exact shape (JSON-serializable):

```python
{
    "data": ...,              # tool-specific payload, see below
    "cypher": "MATCH ...",    # the exact Cypher string executed (with $params, not interpolated values)
    "params": {...},          # the parameter dict passed alongside `cypher`
    "path": {
        "nodes": [
            {"id": "svc:cartservice", "label": "Service", "name": "cartservice", "synthetic": False}
        ],
        "edges": [
            {"source": "svc:frontend", "target": "svc:cartservice", "type": "DEPENDS_ON", "synthetic": False}
        ]
    }
}
```

- `path.nodes` / `path.edges` must contain every node/edge actually touched by the query, deduplicated, in a form the frontend can drop straight into `react-force-graph-2d` (plus `label`/`type` and `synthetic` so the UI can style real vs. synthetic differently). If a tool call touches no graph data (e.g. a pure LLM step), it still returns the shape with empty `nodes`/`edges` lists and an empty/explanatory `cypher`.
- If the underlying query errors, raise — don't swallow. The API layer (`api/`) is responsible for turning exceptions into `{"type": "error", ...}` SSE events.

## Module location

All functions live in `graph/tools.py` (one flat module so the agent's tool registry can introspect it easily). Implementation detail (Cypher building, algorithm helpers) can live in `graph/queries.py`, `graph/algorithms.py`, etc., but `graph/tools.py` is the only import surface other folders use:

```python
from graph.tools import (
    search_entities, blast_radius, failure_path, find_owners, find_experts,
    similar_incidents, trace_decision, critical_services,
    single_points_of_failure, team_clusters, create_incident_issue,
)
```

## Function signatures

### `search_entities(text: str) -> dict`
Free-text search across node names/ids (any label). Case-insensitive substring/fuzzy match on `name`.

```python
def search_entities(text: str) -> dict: ...
```
`data` shape:
```json
{"matches": [{"id": "svc:cartservice", "label": "Service", "name": "cartservice", "synthetic": false}]}
```

### `blast_radius(service: str, max_depth: int = 4) -> dict`
`service` is a `Service.id` (e.g. `"svc:cartservice"`) or bare name (resolve bare names to `svc:<name>` if no colon present). Walks **incoming** `DEPENDS_ON` edges up to `max_depth` hops — i.e. everything that transitively depends on `service` and therefore breaks if it goes down.

```python
def blast_radius(service: str, max_depth: int = 4) -> dict: ...
```
`data` shape:
```json
{
  "root": "svc:cartservice",
  "affected": [
    {"id": "svc:frontend", "name": "frontend", "depth": 1, "synthetic": false}
  ]
}
```

### `failure_path(from_service: str, to_service: str) -> dict`
Shortest dependency path(s) from `from_service` to `to_service` along `DEPENDS_ON` edges (either direction — this answers "how does a failure in A reach B", so traverse A's incoming-dependency chain toward B, or if no such path exists, report that explicitly rather than guessing direction).

```python
def failure_path(from_service: str, to_service: str) -> dict: ...
```
`data` shape:
```json
{"exists": true, "hops": 2, "path_ids": ["svc:a", "svc:b", "svc:c"]}
```
If no path: `{"exists": false, "hops": null, "path_ids": []}`, `path.nodes`/`path.edges` still show the two endpoint nodes (no edges).

If `from_service` has no directed incoming-dependency chain reaching `to_service` but the two are connected when direction is ignored (e.g. they share a common dependency), fall back to the undirected shortest path and say so explicitly rather than reporting a false negative: `{"exists": true, "hops": 2, "path_ids": [...], "direction": "undirected"}`. The `direction` key is only present in this fallback case — its absence means the path found was the normal directed one.

### `find_owners(service: str) -> dict`
Walks `Team -[:OWNS]-> Service` then `Person -[:MEMBER_OF]-> Team`.

```python
def find_owners(service: str) -> dict: ...
```
`data` shape:
```json
{
  "team": {"id": "team:payments", "name": "Payments"},
  "members": [{"id": "person:alice", "name": "Alice", "github_login": "alice"}],
  "teams": [
    {"id": "team:payments", "name": "Payments", "members": [{"id": "person:alice", "name": "Alice", "github_login": "alice"}]}
  ]
}
```
If a service is owned by more than one team (e.g. primary + secondary `OWNS`), `teams` lists every owning team with its own members (sorted by team id). `team`/`members` stay single-team shaped — the first owning team by id — so single-team callers keep working unchanged; callers that need every owning team should read `teams`.

### `find_experts(service: str, days: int = 180) -> dict`
People who `AUTHORED` a `PR` that `TOUCHED` a `File` `CONTAINS`-ed by `service`, within the last `days` days (based on `PR.merged_at`), ranked by number of qualifying PRs descending.

```python
def find_experts(service: str, days: int = 180) -> dict: ...
```
`data` shape:
```json
{"experts": [{"id": "person:bob", "name": "Bob", "pr_count": 5, "last_touched": "2024-05-01T00:00:00Z"}]}
```

### `similar_incidents(service: str) -> dict`
Past `Incident` nodes where `CAUSED` or `AFFECTED` points at this service (or at a service within 1 hop via `DEPENDS_ON`, to catch "similar neighborhood" incidents), most recent first.

```python
def similar_incidents(service: str) -> dict: ...
```
`data` shape:
```json
{"incidents": [{"id": "incident:inc-003", "name": "Cart latency spike", "severity": "sev2", "started_at": "...", "relation": "CAUSED"}]}
```

### `trace_decision(service: str) -> dict`
`Decision` nodes connected via `DECIDED -> Service`, plus any `CITES -> PR` / `CITES -> Decision` chains, so the UI can show "why is it built this way."

```python
def trace_decision(service: str) -> dict: ...
```
`data` shape:
```json
{"decisions": [{"id": "decision:use-grpc", "name": "Use gRPC for internal calls", "status": "accepted", "decided_at": "...", "cites_prs": ["pr:234"]}]}
```

### `critical_services() -> dict`
PageRank over the `Service` `DEPENDS_ON` subgraph. Must use FalkorDB's built-in graph algorithm procedure (not a hand-rolled Python loop) — check the installed FalkorDB version's exact proc name/signature (e.g. `CALL algo.pageRank(...)`) before hardcoding; if the installed version lacks a built-in, fall back to a documented Cypher-based approximation and note it in a comment.

```python
def critical_services() -> dict: ...
```
`data` shape:
```json
{"ranked": [{"id": "svc:productcatalogservice", "name": "productcatalogservice", "score": 0.183}]}
```

### `single_points_of_failure() -> dict`
Betweenness centrality over the same subgraph (again prefer FalkorDB's built-in algo proc if available).

```python
def single_points_of_failure() -> dict: ...
```
`data` shape:
```json
{"ranked": [{"id": "svc:cartservice", "name": "cartservice", "score": 0.47}]}
```

### `team_clusters() -> dict`
Community detection (e.g. Louvain/label propagation — use FalkorDB's built-in if available) over `Service` nodes connected by `DEPENDS_ON`, cross-referenced with `Team` `OWNS` edges to label clusters.

```python
def team_clusters() -> dict: ...
```
`data` shape:
```json
{"clusters": [{"cluster_id": 0, "services": ["svc:a", "svc:b"], "dominant_team": "team:payments"}]}
```

### `create_incident_issue(service: str, summary: str, dry_run: bool = True) -> dict`
Creates (or, if `dry_run=True`, drafts without filing) a GitHub issue on the configured repo (`GITHUB_REPO` env var) summarizing the incident, and writes an `Incident` node + `CAUSED` edge into the graph either way (so the trace/UI has something to show even in dry-run). When `dry_run=False`, actually calls the GitHub API (needs `GITHUB_TOKEN`) and stores the real issue URL/number.

```python
def create_incident_issue(service: str, summary: str, dry_run: bool = True) -> dict: ...
```
`data` shape:
```json
{
  "issue_id": "issue:draft-7f3a",
  "dry_run": true,
  "url": "draft",
  "incident_id": "incident:inc-2024-10-17-cartservice",
  "title": "[Blast Radius] Incident: cartservice"
}
```
When filed for real, `url` is the live GitHub issue URL and `issue_id` is `issue:<number>`.

## Error conventions

- Unknown `service` id/name → raise `ValueError(f"unknown service: {service}")`. Callers (the agent loop) catch this and surface it as a normal tool error, not a crash.
- All Cypher must be parameterized (`$service`, `$max_depth`, etc.) — never f-string a value into the query body. This is a hard rule (see `AGENTS.md`), including for `create_incident_issue`'s writes.

## Agent-facing tool schema (for LLM function calling)

`agent/` wraps each function above into the provider's function-calling schema (Gemini `google-genai` native tools / Groq OpenAI-style tools). The JSON schema per tool should mirror the Python signature 1:1 — param names, types, and defaults identical — so there is no translation layer to keep in sync beyond type mapping (`str`→`"string"`, `int`→`"integer"`, `bool`→`"boolean"`). `agent/` owns generating/maintaining that schema; `graph/` just needs to keep signatures stable and ask the lead before changing one.

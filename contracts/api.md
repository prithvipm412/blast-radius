# API Contract

Owner: **lead only**. Implemented in `api/` (lead). `web/` (Codex 3) consumes this — mock against the example payloads below until the real backend is up.

Base URL in dev: `http://localhost:8000` (`API_HOST`/`API_PORT` in `.env`). Frontend reads `NEXT_PUBLIC_API_URL`.

All endpoints are prefixed `/api`.

---

## `POST /api/ask`

Ask the agent a free-form question. Streams back an SSE response as the agent reasons, calls graph tools, and answers.

**Request body**
```json
{"question": "What breaks if cartservice goes down?", "mode": "graph"}
```
- `mode`: `"graph"` (use FalkorDB tools, the real product mode) or `"rag"` (plain text-only baseline for comparison — no tool calls, no graph). Default `"graph"`.

**Response**: `Content-Type: text/event-stream`. Each SSE `data:` line is one JSON event, one of:

```json
{"type": "tool_call", "tool": "blast_radius", "args": {"service": "svc:cartservice", "max_depth": 4}}
```
```json
{"type": "tool_result", "tool": "blast_radius", "result": { "...full tool dict from contracts/tools.md..." }}
```
```json
{"type": "answer", "text": "If cartservice goes down, frontend and checkoutservice will fail...", "done": true}
```
```json
{"type": "error", "message": "unknown service: svc:bogus"}
```

Streaming notes:
- `answer` events may be sent incrementally with `"done": false` for partial text chunks (token-by-token or sentence-by-sentence streaming from the LLM), followed by one final `"done": true` event containing the complete text in `text`. Frontend should concatenate `done:false` chunks and replace with the final `done:true` text once it arrives.
- The stream ends when the HTTP connection closes after the final `answer` (or `error`) event. No special `[DONE]` sentinel.
- Every `tool_call`/`tool_result` pair uses the same `tool` name and corresponds 1:1 (result always follows its call, no interleaving of two in-flight tool calls in v1 — tool calls are sequential).

---

## `POST /api/alert`

Simulates an alert firing on a service and runs the full canned investigation (blast radius → owners → experts → similar incidents → decisions), streamed the same way as `/api/ask` (reuses the SSE event shape), ending with a synthesized incident note as the final `answer`.

**Request body**
```json
{"service": "cartservice"}
```

**Response**: same SSE event stream shape as `/api/ask`. Expect a `tool_call`/`tool_result` pair for each of `blast_radius`, `find_owners`, `find_experts`, `similar_incidents`, `trace_decision`, then a final `answer` containing the drafted incident note (markdown text). The agent may optionally also call `create_incident_issue` (dry-run by default) as a final tool step before the `answer`.

---

## `GET /api/graph`

Fetch a neighborhood of the graph for visualization, independent of any agent run.

**Query params**
- `focus` (string, optional): node id to center on, e.g. `svc:cartservice`. If omitted, returns the whole graph (capped — see `graph/` implementation for a sane cap, e.g. 500 nodes).
- `depth` (int, optional, default `2`): hops out from `focus`.

**Example**: `GET /api/graph?focus=svc:cartservice&depth=2`

**Response**
```json
{
  "nodes": [
    {"id": "svc:cartservice", "label": "Service", "name": "cartservice", "synthetic": false}
  ],
  "edges": [
    {"source": "svc:frontend", "target": "svc:cartservice", "type": "DEPENDS_ON", "synthetic": false}
  ]
}
```
Same node/edge shape as the `path` field in `contracts/tools.md` — the frontend should be able to reuse one rendering component for both.

This endpoint never returns the `SyncMeta` node or any `operational: true` node/edge — see `contracts/schema.md`'s "Operational metadata" section. There is exactly one such node today (`meta:sync`); it's bookkeeping, not something to visualize.

---

## `GET /api/stats`

Quick counts for a dashboard header.

**Response**
```json
{
  "nodes_by_label": {"Service": 11, "Person": 48, "PR": 320, "Incident": 6, "Decision": 4},
  "edges_by_type": {"DEPENDS_ON": 15, "AUTHORED": 320, "OWNS": 4},
  "synthetic_node_count": 25,
  "real_node_count": 379,
  "last_synced_at": "2024-10-17T10:00:00Z"
}
```
`nodes_by_label`, `synthetic_node_count`, and `real_node_count` exclude operational nodes (`SyncMeta`) — same rule as `GET /api/graph` above. `last_synced_at` is read directly from the `SyncMeta` node's (`id: "meta:sync"`) `last_synced_at` property, written by `ingest.sync()` (via `graph/writer.py`'s `set_sync_meta()`, see `contracts/schema.md`); it is `null` if `/api/sync` has never run.

---

## `POST /api/sync`

Triggers `ingest/` to (re)load real data from GitHub and rebuild the synthetic layer. Long-running — returns immediately with a job acknowledgment; v1 can run synchronously and just block until done (hackathon scope), but the response shape anticipates async:

**Request body**: `{}` (no params in v1)

**Response**
```json
{"status": "ok", "started_at": "2024-10-17T10:00:00Z", "finished_at": "2024-10-17T10:04:12Z"}
```

---

## Error shape (all endpoints)

Non-streaming endpoints (`/api/graph`, `/api/stats`, `/api/sync`) return standard FastAPI HTTP errors on failure:
```json
{"detail": "unknown service: svc:bogus"}
```
with an appropriate 4xx/5xx status code. Streaming endpoints (`/api/ask`, `/api/alert`) never raise an HTTP error after the stream has started — they emit a terminal `{"type": "error", "message": "..."}` SSE event instead, since headers are already sent.

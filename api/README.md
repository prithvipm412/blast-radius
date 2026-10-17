# api/ — owner: lead

`main.py` — FastAPI app implementing every endpoint in `contracts/api.md`:

- `POST /api/ask`, `POST /api/alert` — SSE (`sse_starlette`), streaming `agent.loop`'s `run_ask`/`run_alert` generators straight through.
- `GET /api/graph`, `GET /api/stats` — backed by `agent.registry.graph_neighborhood`/`graph_stats`.
- `POST /api/sync` — calls `ingest.sync.sync()`; returns `501` until `ingest/` lands that module on `main`.

CORS is restricted to `http://localhost:3000` (the Next.js dev server).

Run: `uvicorn api.main:app --reload --port 8000`

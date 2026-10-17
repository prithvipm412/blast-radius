# api/ — owner: lead

Not built yet — next task after this skeleton. Will contain:

- FastAPI app exposing exactly the endpoints in `contracts/api.md`: `POST /api/ask`, `POST /api/alert` (both SSE via `sse-starlette`), `GET /api/graph`, `GET /api/stats`, `POST /api/sync`.
- Wires `agent/` (the LLM loop) and `graph/tools` / `ingest/sync` together behind those endpoints.
- CORS configured for the Next.js dev server in `web/`.

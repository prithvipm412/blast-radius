# web/ — owner: Codex 3

Read `contracts/api.md` first — every fetch call and SSE handler should match it exactly.

## Scope

Next.js (App Router) + TypeScript + Tailwind + `react-force-graph-2d`. Dark navy theme, smooth animations.

- A chat-style view that hits `POST /api/ask` (SSE) and renders `tool_call` → `tool_result` → `answer` events as they stream in, with each tool call's Cypher shown (e.g. in a collapsible "trace" panel) and its `path.nodes`/`path.edges` highlighted on the graph view.
- An "alert" view/button that hits `POST /api/alert` with a chosen service and shows the same streamed trace, ending in a drafted incident note.
- A graph visualization (`react-force-graph-2d`) backed by `GET /api/graph?focus=&depth=`, which also doubles as the live highlight surface during an `/ask`/`/alert` run — union in whatever `path.nodes`/`path.edges` the latest `tool_result` event carries, visually distinct for `synthetic: true` vs `false` nodes/edges.
- A small stats header from `GET /api/stats`.
- A "sync" action calling `POST /api/sync` (expect it to block for a bit — show a loading state).

This folder does not need FalkorDB running to start: mock `/api/*` responses using the example payloads in `contracts/api.md` (e.g. an MSW handler or a simple local JSON fixture server) until `api/` is live, then point `NEXT_PUBLIC_API_URL` at it.

## Getting started

```
cd web
npm install   # or pnpm/yarn — pick one and commit the lockfile
npm run dev
```

Set `NEXT_PUBLIC_API_URL` in `web/.env.local` (gitignored) — see `.env.example` at repo root for the variable name.

## Hard rules (see AGENTS.md)

- Match `contracts/api.md` event/field names exactly — don't invent your own shape and ask the backend to conform later.
- Don't edit `contracts/`, `agent/`, `api/`, `ingest/`, or `graph/`. If the API contract is missing something you need from the UI, ask the human to relay it to the lead.

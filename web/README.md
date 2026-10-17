# Blast Radius UI

Next.js App Router, TypeScript, Tailwind, Framer Motion and a client-only `react-force-graph-2d` canvas. All UI code is in `web/`; API shapes follow `contracts/`.

## Run the demo

```sh
cd web
npm ci
NEXT_PUBLIC_MOCK=1 npm run dev
```

Open http://localhost:3000. Click the lightning button beside **cartservice**. The demo streams six sequential tool calls, highlights incoming dependencies, shows ownership and incident context, then renders a markdown brief and **Drafted issue** card. Click a service or graph node to inspect properties. Expand **View Cypher** for the parameterized query and copy control.

For a persistent local setting, copy `.env.example` to `.env.local`. Never commit `.env.local`.

## Live backend

```sh
NEXT_PUBLIC_MOCK=0 NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

The frontend reads `/api/graph` and `/api/stats`, posts `/api/ask` and `/api/alert` using fetch + ReadableStream, and supports `/api/sync`. The backend must allow CORS from the frontend origin. Public environment variables are compiled into production builds: rebuild when changing modes or API URLs.

```sh
NEXT_PUBLIC_MOCK=1 npm run build
npm start
npm test
```

## Demo controls and provenance

- **Graph vs Plain RAG** → **Compare answers** sends the same question in `graph` and `rag` modes concurrently. In mock mode both responses are illustrative fixtures.
- Green/amber/red service dots show local simulated impact, not production health. The API contract has no health endpoint.
- Mock stats reproduce the API example (404 entities); the canvas contains a smaller neighborhood fixture, with its own displayed node/edge counts.
- Solid nodes/edges represent repository-derived service dependencies. Dashed outlines/edges identify synthetic context. All mock execution is labeled; mock Cypher is displayed for illustration and is not executed.
- The fixture includes synthetic ownership, incidents, and decisions. It intentionally returns no experts instead of fabricating GitHub history.
- Issue creation in the mock is always a dry run. Live `dry_run:false` results render **Filed issue** with the returned GitHub URL. The UI does not override the backend's dry-run policy.
- Stop cancels active requests and preserves partial results. Network, HTTP, terminal SSE errors and incomplete streams appear as notifications.

## Validation

`npm test` checks split UTF-8/CRLF SSE parsing, partial/final answers, terminal errors, malformed/truncated streams, and the full cart alert fixture. The graph is dynamically imported with `ssr:false`; fonts are bundled locally so builds require no font-provider access.

The intended desktop layout is 1280px and wider. Sidebars scroll independently; graph controls support pan, zoom, fit-to-view, and node inspection.

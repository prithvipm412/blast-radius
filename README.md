# Blast Radius

On-call agent with a company brain, backed by FalkorDB. Graph Hacks hackathon entry (WeMakeDevs x FalkorDB).

When an alert fires on a service, the agent walks a knowledge graph to find the blast radius, the owners/experts, similar past incidents, and the decisions behind the current setup — then drafts an incident note and (dry-run by default) opens a GitHub issue. Every answer shows its trace: the tool calls, the Cypher that ran, and the graph path, so the UI can highlight it.

Tracks: 01 "Agents That Act on Connected Data" + 03 "Company Brain". FalkorDB does real work here — the product does not function without it.

## Start here

- **Read `AGENTS.md` first.** It defines folder ownership and the hard rules (parameterized Cypher, never edit `contracts/`, never commit `.env`, etc.) for everyone working on this repo.
- `contracts/` is the ground truth for schema, tool signatures, and the HTTP/SSE API. Read it before writing code in `ingest/`, `graph/`, or `web/`.

## Repo layout

```
contracts/   schema.md, tools.md, api.md — the interfaces everything else is built against (lead owns)
agent/       LLM provider abstraction + agentic loop (lead owns)
api/         FastAPI app, SSE streaming (lead owns)
ingest/      GitHub loader + synthetic data + sync (Codex 1 owns)
graph/       FalkorDB client, all Cypher, algorithms, MCP server (Codex 2 owns)
web/         Next.js frontend (Codex 3 owns)
scripts/     one-off operational scripts (check_db.py, etc.)
docs/        extra documentation
tests/       tests + tests/fixtures/ (shared sample data)
```

## Setup

### Backend (Python 3.12)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# or: pip install -r requirements.txt
```

### Environment

```bash
cp .env.example .env
# fill in FALKORDB_*, LLM_PROVIDER + its API key, GITHUB_TOKEN
```

Never commit `.env` — it's gitignored.

### Sanity-check the DB connection

```bash
python scripts/check_db.py
```
Should print `OK` after connecting to FalkorDB, running `RETURN 1`, and creating/deleting a test node.

### Frontend (Next.js)

```bash
cd web
npm install
cp ../.env.example .env.local   # keep only NEXT_PUBLIC_API_URL
npm run dev
```

## Data

- **Real**: [`GoogleCloudPlatform/microservices-demo`](https://github.com/GoogleCloudPlatform/microservices-demo) (Online Boutique, Apache-2.0) — services, service dependency edges (hand-curated from the repo's real call graph), contributors, PRs, issues.
- **Synthetic** (clearly flagged `synthetic: true`): teams, on-call ownership, incidents, decisions/ADRs.

See `contracts/schema.md` for the full node/edge reference and which parts of the graph are real vs. synthetic.

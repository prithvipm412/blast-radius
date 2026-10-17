# ingest/ — owner: Codex 1

Read `contracts/schema.md` first.

## Scope

- Load real data from `GoogleCloudPlatform/microservices-demo` (Apache-2.0) via the GitHub API (`PyGithub`, token from `.env` `GITHUB_TOKEN`):
  - Repo metadata → `Repo` node.
  - Services → `Service` nodes. The service list and their source directories are fixed/known (frontend, cartservice, checkoutservice, paymentservice, productcatalogservice, currencyservice, shippingservice, emailservice, recommendationservice, adservice, loadgenerator) — confirm against the repo's current `src/` layout.
  - Files → `File` nodes, `CONTAINS` edges (`Repo -> File` and `Service -> File` by path prefix).
  - Contributors → `Person` nodes.
  - PRs → `PR` nodes, `AUTHORED` (`Person -> PR`), `TOUCHED` (`PR -> File`, from the PR's changed files).
  - Issues → `Issue` nodes, `MENTIONS` (`Issue -> Service`, via text match against service names in title/body).
- Service dependency edges (`DEPENDS_ON`, `Service -> Service`): hand-curate as JSON from the repo's real service call graph (gRPC calls between services — see the repo's `README.md`/architecture diagram for the real topology), check it into `ingest/data/service_dependencies.json`, and load it as part of sync. This is "derived from the repo" per the brief, not invented.
- Synthetic layer: `Team`, `Incident`, `Decision`, `Doc` (runbooks) nodes and their edges (`OWNS`, `MEMBER_OF`, `CAUSED`, `AFFECTED`, `RESOLVED_BY`, `DECIDED`, `CITES`, synthetic `MENTIONS`/`Doc` mentions). Hand-curate as JSON too — check into `ingest/data/synthetic_layer.json`. **Must set `synthetic: true`** on everything in this layer per `contracts/schema.md`.
- A `sync()` entrypoint that `api/`'s `POST /api/sync` calls (or a CLI script under `scripts/` if easier initially) — wipes and reloads, or upserts idempotently, into FalkorDB via `graph/` (import `graph.tools`/`graph.client`, don't write your own Cypher — ask the lead if you need a new graph-side primitive).

## Suggested layout

```
ingest/
  __init__.py
  github_loader.py      # PyGithub calls -> raw records
  synthetic_data.py      # loads ingest/data/synthetic_layer.json
  data/
    service_dependencies.json
    synthetic_layer.json
  sync.py                 # orchestrates: fetch -> transform -> write via graph/
```

## Hard rules (see AGENTS.md)

- Real data must actually come from the GitHub API or the repo itself — no fabricating PRs/issues/contributors.
- Synthetic data must be clearly flagged `synthetic: true` per `contracts/schema.md`.
- Don't write raw Cypher here — call into `graph/`'s functions to persist what you've fetched/curated. If `graph/` doesn't expose a write primitive you need, ask the human to relay it to the lead rather than writing your own Cypher client.
- Respect GitHub API rate limits — cache/paginate sensibly, don't hammer the API on every `/api/sync` call during the hackathon.

## Getting started

1. `cp .env.example .env`, fill in `GITHUB_TOKEN` (a personal token with public repo read is enough).
2. Start against `tests/fixtures/sample_graph.json` to understand the target shape before writing the real loader.

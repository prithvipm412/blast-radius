# Graph Schema — `blast_radius`

Owner: **lead only**. Everyone else: read this, don't edit it. Propose changes by asking the human to relay them to the lead.

FalkorDB graph name: `blast_radius` (set via `FALKORDB_GRAPH` in `.env`).

> **Changelog**: this revision resolves the blockers `ingest/` reported in `CONTRACT_BLOCKERS.md` — adds `Commit` and `SyncMeta` node labels, Issue labels/authorship/linked-PR edges, CODEOWNERS representation, a decisive synthetic-edge rule, `Decision -> Doc` `CITES`, a decisive `source_url` rule for synthetic nodes, and a graph write interface for bulk loaders. Everything added is additive (new node labels, new edge rows, new properties) — nothing already-implemented against the prior version of this file needs to change.

## Conventions

- Every node has at minimum: `id` (string, globally unique, stable across re-ingest), `name` (string, human-readable), `source_url` (string, citation — repo URL, PR URL, issue URL, or `"synthetic"` if none exists), `synthetic` (bool — `true` if this node was fabricated for the demo rather than derived from the real repo/GitHub history).
- IDs are namespaced by type to avoid collisions, e.g. `svc:cartservice`, `person:someuser`, `pr:12345`, `incident:inc-003`.
- Timestamps are ISO-8601 strings (`2024-03-11T10:00:00Z`), stored as strings (FalkorDB/Cypher has no native datetime index requirement here — keep it simple, parse in Python when needed).
- All writes from application code MUST use parameterized Cypher (`$param`), never string-interpolated values. See `AGENTS.md`.
- An **operational** node or edge (currently only `SyncMeta`) carries `operational: true` and represents sync/infrastructure bookkeeping, not a product entity. Operational nodes/edges are excluded from `GET /api/graph`, `GET /api/stats` counts, and any UI visualization — see "Operational metadata" below. `operational` defaults to (and is omitted/`false` for) every other label.

## `source_url` for synthetic nodes — decisive rule

For every synthetic node (`Team` where `team_kind="oncall"`, `Incident`, `Decision`, `Doc` where `kind` is a synthetic kind like `"runbook"`), `source_url` **MUST be the literal string `"synthetic"`** — never a path into `ingest/data/*.json`. These nodes have no real external citation to show; `"synthetic"` is also the sentinel the UI checks to avoid rendering a dead/non-clickable link. The local JSON file a fabricated node was loaded from is ingest-side provenance, not a citation, and is not encoded in the graph.

## Node labels

### `Person`
Real GitHub contributors (and synthetic on-call engineers).
| property | type | notes |
|---|---|---|
| id | string | `person:<github_login>` |
| name | string | display name or login |
| source_url | string | `https://github.com/<login>` or `synthetic` |
| synthetic | bool | |
| github_login | string | nullable for synthetic-only people |
| role | string | e.g. "SRE", "backend engineer" (synthetic ok) |

### `Team`
Two kinds of team, disambiguated by `team_kind` and by ID prefix so they never collide:
- **Synthetic on-call teams** (hand-curated, per the original brief): `team_kind="oncall"`, `id = team:<slug>` (e.g. `team:payments`), `synthetic=true`, `source_url="synthetic"`.
- **Real GitHub teams** (from `CODEOWNERS`, e.g. `@GoogleCloudPlatform/some-team`): `team_kind="github"`, `id = team:gh:<org>/<slug>` (e.g. `team:gh:GoogleCloudPlatform/cart-owners`), `synthetic=false`, `source_url = https://github.com/orgs/<org>/teams/<slug>`. A GitHub team is **not** a `Person` — it is always a `Team` with `team_kind="github"`, even though it can appear directly in `CODEOWNERS` as an owner.

| property | type | notes |
|---|---|---|
| id | string | `team:<slug>` (oncall) or `team:gh:<org>/<slug>` (github) |
| name | string | |
| source_url | string | `synthetic` (oncall) or team URL (github) |
| synthetic | bool | `true` (oncall) / `false` (github) |
| team_kind | string | `"oncall"` \| `"github"` |
| github_handle | string | nullable; `@org/slug` form, set only for `team_kind="github"` |
| pager_channel | string | e.g. `#pager-payments`; nullable, set only for `team_kind="oncall"` |

### `Service`
Microservices from the Online Boutique demo.
| property | type | notes |
|---|---|---|
| id | string | `svc:<service_name>` e.g. `svc:cartservice` |
| name | string | e.g. `cartservice` |
| source_url | string | path in repo, e.g. `https://github.com/GoogleCloudPlatform/microservices-demo/tree/main/src/cartservice` |
| synthetic | bool | `false` |
| language | string | e.g. "Go", "C#", "Python" |
| description | string | short description from repo README |
| criticality | float | nullable, populated by `critical_services()` (PageRank score), not hand-set |

### `Repo`
One node for the source repo (singleton in v1, but modeled as a label in case more repos are added).
| property | type | notes |
|---|---|---|
| id | string | `repo:<owner>/<name>` e.g. `repo:GoogleCloudPlatform/microservices-demo` |
| name | string | `GoogleCloudPlatform/microservices-demo` |
| source_url | string | repo URL |
| synthetic | bool | `false` |
| default_branch | string | |

### `File`
Source files, used to connect PRs/commits to services via path.
| property | type | notes |
|---|---|---|
| id | string | `file:<path>` e.g. `file:src/cartservice/main.go` |
| name | string | basename |
| source_url | string | blob URL on GitHub |
| synthetic | bool | `false` |
| path | string | full path within repo |

### `Commit`
Real commits (up to the ~300 requested). Resolves blocker #1.
| property | type | notes |
|---|---|---|
| id | string | `commit:<sha>` (full SHA) |
| name | string | first line of the commit message (subject) |
| source_url | string | commit URL, e.g. `https://github.com/GoogleCloudPlatform/microservices-demo/commit/<sha>` |
| synthetic | bool | `false` |
| sha | string | full SHA, same value as the `id` suffix |
| message | string | full commit message (truncate if huge, same convention as `PR.body`) |
| authored_at | string | ISO-8601 |

### `PR`
Pull requests from the real repo.
| property | type | notes |
|---|---|---|
| id | string | `pr:<number>` |
| name | string | PR title |
| source_url | string | PR URL |
| synthetic | bool | `false` |
| number | int | |
| merged_at | string | ISO-8601, nullable |
| body | string | PR description (truncated if huge) |

### `Issue`
GitHub issues (both ingested real issues and ones created by `create_incident_issue`). Resolves blocker #2.
| property | type | notes |
|---|---|---|
| id | string | `issue:<number>` for real; `issue:draft-<uuid>` for dry-run drafts not yet filed |
| name | string | issue title |
| source_url | string | issue URL, or `"draft"` if dry-run and unfiled |
| synthetic | bool | `true` if created by the agent, `false` if ingested from real repo |
| number | int | nullable until filed |
| state | string | "open" / "closed" / "draft" |
| body | string | |
| labels | list[string] | GitHub label names, e.g. `["bug", "p1"]`; `[]` if none |

### `Incident`
Synthetic past incidents (and live ones created via `/api/alert`).
| property | type | notes |
|---|---|---|
| id | string | `incident:<slug>` |
| name | string | short title, e.g. "Cart service latency spike" |
| source_url | string | `synthetic` (see the decisive rule above — this never changes even once `RESOLVED_BY`/`CAUSED` point at a real PR) |
| synthetic | bool | `true` |
| summary | string | |
| severity | string | "sev1".."sev4" |
| started_at | string | ISO-8601 |
| resolved_at | string | ISO-8601, nullable |

### `Decision`
Synthetic ADRs / architectural decisions.
| property | type | notes |
|---|---|---|
| id | string | `decision:<slug>` |
| name | string | ADR title |
| source_url | string | `synthetic` |
| synthetic | bool | `true` |
| status | string | "proposed" / "accepted" / "superseded" |
| context | string | why the decision was made |
| decided_at | string | ISO-8601 |

### `Doc`
Generic documentation node (READMEs, runbooks — mostly synthetic runbooks + real READMEs).
| property | type | notes |
|---|---|---|
| id | string | `doc:<slug>` |
| name | string | doc title |
| source_url | string | repo URL (real README) or `synthetic` (runbook/postmortem) |
| synthetic | bool | `false` for `kind="readme"`, `true` for `kind="runbook"` / `"postmortem"` |
| kind | string | "readme" / "runbook" / "postmortem" |
| body | string | |

### `SyncMeta`
Singleton operational bookkeeping node for incremental sync. Resolves blocker #4. **Not a product entity** — see "Operational metadata" below.
| property | type | notes |
|---|---|---|
| id | string | always `meta:sync` (singleton, `MERGE`d in place on every sync) |
| name | string | `"sync metadata"` |
| source_url | string | `"internal"` |
| synthetic | bool | `false` |
| operational | bool | always `true` |
| last_synced_at | string | ISO-8601, updated at the end of every successful `ingest.sync()` run — this is the value `GET /api/stats`'s `last_synced_at` field returns |
| last_synced_commit_sha | string | nullable; the most recent `Commit.sha` observed, for incremental sync watermarking |
| last_synced_issue_number | int | nullable; same idea, for issues/PRs |

## Edge types

All edges carry at minimum: `source_url` (nullable, provenance of the edge itself), `synthetic` (bool). Direction is `(from)-[:EDGE]->(to)` as listed. Where one edge *type* legitimately connects more than one pair of node labels (e.g. `CONTAINS`, `AUTHORED`, `TOUCHED`, `CITES`), each pair gets its own row below with its own `synthetic` value — the type name is shared, the semantics and `synthetic` value are per-row.

| edge | from → to | meaning | key properties |
|---|---|---|---|
| `DEPENDS_ON` | `Service -> Service` | caller depends on callee (real call graph) | `synthetic=false`, `weight` (call frequency estimate, default 1.0) |
| `OWNS` | `Team -> Service` | on-call team owns/operates the service (synthetic) | `synthetic=true`, `role` ("primary"/"secondary") |
| `OWNS` | `Team -> File` | `CODEOWNERS` entry: a GitHub team owns this file (real) | `synthetic=false`, `pattern` (the original `CODEOWNERS` glob, e.g. `src/cartservice/*`) |
| `OWNS` | `Person -> File` | `CODEOWNERS` entry: an individual owns this file (real) | `synthetic=false`, `pattern` |
| `MEMBER_OF` | `Person -> Team` | person belongs to team — on-call (`Team.team_kind="oncall"`) or GitHub (`"github"`) | `synthetic` = `true` for oncall teams, `false` for github teams (membership is read from the real GitHub team roster), `since` (nullable for github teams if GitHub doesn't give you a join date) |
| `AUTHORED` | `Person -> PR` | person opened the PR (real) | `synthetic=false` |
| `AUTHORED` | `Person -> Issue` | person opened the issue (real). Resolves blocker #2. | `synthetic=false` |
| `AUTHORED` | `Person -> Commit` | person authored the commit (real). Resolves blocker #1. | `synthetic=false` |
| `TOUCHED` | `PR -> File` | PR modifies file (real, from PR diff) | `synthetic=false`, `additions`, `deletions` |
| `TOUCHED` | `Commit -> File` | commit modifies file (real, from commit diff). Resolves blocker #1. | `synthetic=false`, `additions`, `deletions` |
| `CONTAINS` | `Repo -> File` | file belongs to repo (real) | `synthetic=false` |
| `CONTAINS` | `Service -> File` | file belongs to service's directory (real, derived from path prefix) | `synthetic=false` |
| `CAUSED` | `Incident -> Service` | incident originated in / was caused by this service (synthetic narrative) | `synthetic=true` |
| `CAUSED` | `Incident -> PR` | the PR identified (by the fabricated incident narrative) as the root-cause artifact — e.g. a bad deploy. The PR node itself can be, and usually is, real. Resolves blocker #5. | `synthetic=true` (always — see the synthetic-edge rule below) |
| `AFFECTED` | `Incident -> Service` | incident's blast radius touched this service (synthetic) | `synthetic=true` |
| `RESOLVED_BY` | `Incident -> PR` | the fix PR the fabricated incident narrative credits with resolving it. The PR node itself can be real. | `synthetic=true` (always — see the synthetic-edge rule below. Resolves blocker #6.) |
| `RESOLVED_BY` | `Issue -> PR` | the real "linked PR" GitHub reports as closing/resolving this issue. Resolves blocker #2. | `synthetic=false` |
| `DECIDED` | `Decision -> Service` | decision governs/applies to this service (synthetic) | `synthetic=true` |
| `CITES` | `Decision -> PR` | decision references the PR credited (by the fabricated decision narrative) with implementing it. The PR node itself can be real. | `synthetic=true` (always — see the synthetic-edge rule below. Resolves blocker #6.) |
| `CITES` | `Decision -> Doc` | decision references supporting documentation, e.g. a runbook or README (synthetic). Resolves blocker #7. | `synthetic=true` |
| `CITES` | `Incident -> Decision` | an incident's postmortem cites a prior decision as context (synthetic) | `synthetic=true` |
| `MENTIONS` | `Issue -> Service` | issue text mentions/affects a service (real, via text match) | `synthetic=false` |
| `MENTIONS` | `Doc -> Service` | doc describes/references a service | `synthetic` = false for README, true for runbook |

### Synthetic-edge rule — decisive (resolves blocker #6)

`synthetic` on an **edge** means *"the relationship this edge asserts was fabricated for the demo, not observed in real history"* — it is independent of whether the edge's endpoint nodes are themselves real or synthetic. Concretely:

- **Any edge where `Incident` or `Decision` is the source is always `synthetic=true`, with no exception** — including `CAUSED -> PR`, `RESOLVED_BY -> PR`, and `CITES -> PR`/`CITES -> Doc`. Even when the target PR is a real, merged pull request, the *claim* "this incident was caused by / resolved by / this decision cites that PR" is a fabricated narrative link we invented for the demo, and must not be presented as verified historical fact. The previous wording ("synthetic = true unless linked to a real merged PR") is retracted — it was wrong and is exactly what `ingest/` flagged.
- Conversely, an edge between two real-world entities carrying real GitHub data (`DEPENDS_ON`, `AUTHORED`, `TOUCHED`, `CONTAINS`, `MENTIONS -> Service`, `RESOLVED_BY` on `Issue -> PR`, `OWNS`/`MEMBER_OF` where the team is `team_kind="github"`) is `synthetic=false`.
- A `Team` node's own `synthetic` flag still follows `team_kind` (`true` for oncall, `false` for github) per its node table above — that part was already correct and is unchanged.

When in doubt: **ask "did this edge get its existence from GitHub's history, or did a human/LLM write it into `ingest/data/*.json` as part of the demo narrative?"** The former is `false`; the latter is always `true`, regardless of what it points at.

### Operational metadata (resolves blocker #4)

`SyncMeta` (`operational: true`) is bookkeeping, not a graph entity the product reasons about. It:
- **is** read/written by `ingest.sync()` (via the graph write interface below) to track `last_synced_at` and incremental-sync watermarks;
- **is** the source of truth for `GET /api/stats`'s `last_synced_at` field (see `contracts/api.md`);
- **is not** counted in `GET /api/stats`'s `nodes_by_label`, `synthetic_node_count`, or `real_node_count`;
- **is not** returned by `GET /api/graph`, and is never part of any tool's `path.nodes`/`path.edges`.

Any future operational node/edge follows the same rule via the shared `operational: true` flag — no per-label special-casing needed.

### Notes on direction choices (so tool implementations are consistent)

- `AFFECTED` / `CAUSED` both point **away from** `Incident` toward their target, so "everything this incident touches" is a simple outgoing traversal from the `Incident` node — this now includes the `CAUSED -> PR` artifact edge, not just `CAUSED -> Service`.
- `DEPENDS_ON` points from the dependent (caller) to the dependency (callee), so blast radius from an outage is computed by walking **incoming** `DEPENDS_ON` edges into the failing service (i.e. "who depends on me" = who breaks when I break).

## CODEOWNERS representation (resolves blocker #3)

Each `CODEOWNERS` line (`<pattern> <owner1> <owner2> ...`) is loaded as:
1. Resolve `<pattern>` to the concrete `File` nodes it matches (ingest already does this — "Independent work completed" in `CONTRACT_BLOCKERS.md`).
2. For each owner token:
   - `@org/team-slug` → a `Team` node with `team_kind="github"`, `id = team:gh:<org>/<team-slug>` (create it if it doesn't exist yet — CODEOWNERS may reference teams never seen elsewhere) → `OWNS` edge `Team -> File`.
   - `@individual-login` or a bare email → a `Person` node, same `id` scheme as everywhere else (`person:<github_login>`; if only an email is given and no login can be resolved, use `person:email:<email>` as a fallback id, still `synthetic=false`) → `OWNS` edge `Person -> File`.
3. Every such `OWNS` edge carries `pattern` = the original glob string from the `CODEOWNERS` line, so multiple `File`s owned by the same line are traceable back to one rule.

## Graph write interface (for `ingest/`)

Resolves the "may `ingest/` own graph writes" question from `CONTRACT_BLOCKERS.md`. **No** — `ingest/` never writes raw Cypher (this was already a hard rule in `AGENTS.md`; it wasn't previously backed by a callable interface, which is the actual gap). `graph/` owns a new module, `graph/writer.py`, exposing bulk, parameterized `UNWIND`-based write primitives that `ingest/` (and `agent/`'s `create_incident_issue`) call instead of writing Cypher themselves:

```python
def ensure_indexes() -> None:
    """Idempotently (re)create every index/constraint in this file's DDL section below.
    Safe to call from ingest.sync() at the start of every run, in addition to graph/'s
    own startup hook — both are idempotent, so calling it twice is a no-op."""

def upsert_nodes(label: str, records: list[dict], key: str = "id") -> dict:
    """Bulk upsert via parameterized UNWIND, keyed on `key` (default "id"). One call per
    label per batch; `records` is a list of property dicts, each including `key`'s value.
    Returns {"upserted": <count>}."""

def upsert_edges(edge_type: str, from_label: str, to_label: str, records: list[dict]) -> dict:
    """Bulk upsert edges via parameterized UNWIND. Each record is
    {"from_id": str, "to_id": str, **edge_properties} (edge_properties must include
    `synthetic`, per this file's synthetic-edge rule, and may include `source_url`).
    `from_label`/`to_label` scope the MATCH on each side for a cheap index hit.
    Returns {"upserted": <count>}."""

def set_sync_meta(last_synced_at: str, **watermarks) -> None:
    """MERGEs the singleton SyncMeta node (id='meta:sync'), setting last_synced_at and
    any watermark kwargs matching SyncMeta's property table (e.g. last_synced_commit_sha=...).
    `ingest.sync()` calls this once, at the end of a successful run."""
```

This is additive to `contracts/tools.md`'s existing 11 agent-facing tools — `graph/writer.py` is a separate, ingest-facing surface (bulk writes), not one of the 11 LLM-callable tools, and is not exposed to the agent loop.

## Indexes & constraints

Run once at startup (idempotent — `graph/` owns the actual execution via `ensure_indexes()` above; `ingest.sync()` may also call it defensively):

```cypher
CREATE INDEX FOR (n:Service) ON (n.id);
CREATE INDEX FOR (n:Person) ON (n.id);
CREATE INDEX FOR (n:Team) ON (n.id);
CREATE INDEX FOR (n:Repo) ON (n.id);
CREATE INDEX FOR (n:File) ON (n.id);
CREATE INDEX FOR (n:Commit) ON (n.id);
CREATE INDEX FOR (n:PR) ON (n.id);
CREATE INDEX FOR (n:Issue) ON (n.id);
CREATE INDEX FOR (n:Incident) ON (n.id);
CREATE INDEX FOR (n:Decision) ON (n.id);
CREATE INDEX FOR (n:Doc) ON (n.id);
CREATE INDEX FOR (n:SyncMeta) ON (n.id);

CREATE INDEX FOR (n:Service) ON (n.name);
CREATE INDEX FOR (n:Person) ON (n.github_login);
CREATE INDEX FOR (n:Commit) ON (n.sha);

CREATE CONSTRAINT FOR (n:Service) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Person) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Team) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Repo) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:File) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Commit) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:PR) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Issue) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Incident) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Decision) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Doc) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:SyncMeta) REQUIRE n.id IS UNIQUE;
```

(`graph/` should wrap these in `IF NOT EXISTS`-style idempotent checks appropriate to the FalkorDB version in use — check the installed version's exact syntax before hardcoding.)

## What's real vs. synthetic (quick reference)

| Real (derived from GoogleCloudPlatform/microservices-demo + GitHub API) | Synthetic (hand-curated for the demo) | Operational (excluded from both) |
|---|---|---|
| `Service`, `Repo`, `File`, `Commit`, `PR`, `Issue` (ingested), `Person` (contributors), `Team` where `team_kind="github"`, `DEPENDS_ON`, `AUTHORED`, `TOUCHED`, `CONTAINS`, `MENTIONS -> Service`, `OWNS` (CODEOWNERS), `MEMBER_OF` (github team), `RESOLVED_BY` on `Issue -> PR` | `Team` where `team_kind="oncall"`, `Incident`, `Decision`, `Doc` where `kind` is `"runbook"`/`"postmortem"`, `OWNS` (on-call), `MEMBER_OF` (oncall team), `CAUSED`, `AFFECTED`, `DECIDED`, `RESOLVED_BY` on `Incident -> PR`, `CITES` | `SyncMeta` |

Every node/edge's `synthetic` flag must match this table — the UI will visually distinguish real vs. synthetic, and the "must not function without FalkorDB" rule depends on graph traversals being real work, not a facade over synthetic-only data.

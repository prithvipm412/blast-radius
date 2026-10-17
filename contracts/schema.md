# Graph Schema — `blast_radius`

Owner: **lead only**. Everyone else: read this, don't edit it. Propose changes by asking the human to relay them to the lead.

FalkorDB graph name: `blast_radius` (set via `FALKORDB_GRAPH` in `.env`).

## Conventions

- Every node has at minimum: `id` (string, globally unique, stable across re-ingest), `name` (string, human-readable), `source_url` (string, citation — repo URL, PR URL, issue URL, or `"synthetic"` if none exists), `synthetic` (bool — `true` if this node was fabricated for the demo rather than derived from the real repo/GitHub history).
- IDs are namespaced by type to avoid collisions, e.g. `svc:cartservice`, `person:someuser`, `pr:12345`, `incident:inc-003`.
- Timestamps are ISO-8601 strings (`2024-03-11T10:00:00Z`), stored as strings (FalkorDB/Cypher has no native datetime index requirement here — keep it simple, parse in Python when needed).
- All writes from application code MUST use parameterized Cypher (`$param`), never string-interpolated values. See `AGENTS.md`.

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
Synthetic on-call / ownership teams.
| property | type | notes |
|---|---|---|
| id | string | `team:<slug>` |
| name | string | |
| source_url | string | `synthetic` |
| synthetic | bool | always `true` |
| pager_channel | string | e.g. `#pager-payments` (synthetic) |

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
GitHub issues (both ingested real issues and ones created by `create_incident_issue`).
| property | type | notes |
|---|---|---|
| id | string | `issue:<number>` for real; `issue:draft-<uuid>` for dry-run drafts not yet filed |
| name | string | issue title |
| source_url | string | issue URL, or `"draft"` if dry-run and unfiled |
| synthetic | bool | `true` if created by the agent, `false` if ingested from real repo |
| number | int | nullable until filed |
| state | string | "open" / "closed" / "draft" |
| body | string | |

### `Incident`
Synthetic past incidents (and live ones created via `/api/alert`).
| property | type | notes |
|---|---|---|
| id | string | `incident:<slug>` |
| name | string | short title, e.g. "Cart service latency spike" |
| source_url | string | `synthetic` (or issue URL if it later gets filed) |
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
| source_url | string | repo URL or `synthetic` |
| synthetic | bool | |
| kind | string | "readme" / "runbook" / "postmortem" |
| body | string | |

## Edge types

All edges carry at minimum: `source_url` (nullable, provenance of the edge itself), `synthetic` (bool). Direction is `(from)-[:EDGE]->(to)` as listed.

| edge | from → to | meaning | key properties |
|---|---|---|---|
| `DEPENDS_ON` | `Service -> Service` | caller depends on callee (real call graph) | `synthetic=false`, `weight` (call frequency estimate, default 1.0) |
| `OWNS` | `Team -> Service` | team owns/operates the service (synthetic) | `synthetic=true`, `role` ("primary"/"secondary") |
| `MEMBER_OF` | `Person -> Team` | person belongs to team (synthetic) | `synthetic=true`, `since` |
| `AUTHORED` | `Person -> PR` | person opened the PR (real) | `synthetic=false` |
| `TOUCHED` | `PR -> File` | PR modifies file (real, from PR diff) | `synthetic=false`, `additions`, `deletions` |
| `CONTAINS` | `Repo -> File` | file belongs to repo (real) | `synthetic=false` |
| `CONTAINS` | `Service -> File` | file belongs to service's directory (real, derived from path prefix) | `synthetic=false` |
| `CAUSED` | `Incident -> Service` | incident originated in / was caused by this service (synthetic) | `synthetic=true` |
| `AFFECTED` | `Incident -> Service` | incident's blast radius touched this service (synthetic) | `synthetic=true` |
| `RESOLVED_BY` | `Incident -> PR` | the fix PR that resolved the incident (can link real PR) | `synthetic` = true unless linked to a real merged PR |
| `DECIDED` | `Decision -> Service` | decision governs/applies to this service (synthetic) | `synthetic=true` |
| `CITES` | `Decision -> PR` | decision references the PR that implemented it (can link real PR) | `synthetic` = true unless linked to a real PR |
| `CITES` | `Incident -> Decision` | an incident's postmortem cites a prior decision as context | `synthetic=true` |
| `MENTIONS` | `Issue -> Service` | issue text mentions/affects a service (real, via text match) | `synthetic=false` |
| `MENTIONS` | `Doc -> Service` | doc describes/references a service | `synthetic` = false for README, true for runbook |

Notes on direction choices (so tool implementations are consistent):
- `AFFECTED` / `CAUSED` both point **away from** `Incident` toward `Service`, so "all services affected by incident X" is a simple outgoing traversal from the `Incident` node.
- `DEPENDS_ON` points from the dependent (caller) to the dependency (callee), so blast radius from an outage is computed by walking **incoming** `DEPENDS_ON` edges into the failing service (i.e. "who depends on me" = who breaks when I break).

## Indexes & constraints

Run once at startup (idempotent — `graph/` owns the actual execution, this is the reference DDL):

```cypher
CREATE INDEX FOR (n:Service) ON (n.id);
CREATE INDEX FOR (n:Person) ON (n.id);
CREATE INDEX FOR (n:Team) ON (n.id);
CREATE INDEX FOR (n:Repo) ON (n.id);
CREATE INDEX FOR (n:File) ON (n.id);
CREATE INDEX FOR (n:PR) ON (n.id);
CREATE INDEX FOR (n:Issue) ON (n.id);
CREATE INDEX FOR (n:Incident) ON (n.id);
CREATE INDEX FOR (n:Decision) ON (n.id);
CREATE INDEX FOR (n:Doc) ON (n.id);

CREATE INDEX FOR (n:Service) ON (n.name);
CREATE INDEX FOR (n:Person) ON (n.github_login);

CREATE CONSTRAINT FOR (n:Service) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Person) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Team) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Repo) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:File) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:PR) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Issue) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Incident) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Decision) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Doc) REQUIRE n.id IS UNIQUE;
```

(`graph/` should wrap these in `IF NOT EXISTS`-style idempotent checks appropriate to the FalkorDB version in use — check the installed version's exact syntax before hardcoding.)

## What's real vs. synthetic (quick reference)

| Real (derived from GoogleCloudPlatform/microservices-demo + GitHub API) | Synthetic (hand-curated for the demo) |
|---|---|
| `Service`, `Repo`, `File`, `PR`, `Issue` (ingested), `Person` (contributors), `DEPENDS_ON`, `AUTHORED`, `TOUCHED`, `CONTAINS`, `MENTIONS` | `Team`, `Incident`, `Decision`, `Doc` (runbooks), `OWNS`, `MEMBER_OF`, `CAUSED`, `AFFECTED`, `DECIDED` |

Every node/edge's `synthetic` flag must match this table — the UI will visually distinguish real vs. synthetic, and the "must not function without FalkorDB" rule depends on graph traversals being real work, not a facade over synthetic-only data.

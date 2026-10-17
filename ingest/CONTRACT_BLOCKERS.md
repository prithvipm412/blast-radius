# Ingestion integration blockers

Graph writes are pending lead clarification under AGENTS.md. No contracts were changed.

1. Define Commit properties and commit-to-person/file edges for the requested 300 commits.
2. Define Issue labels, issue authorship, and linked-PR relationships.
3. Define CODEOWNERS representation (including GitHub team handles, which are not people).
4. Define Meta ID and timestamp property for incremental sync; specify whether operational
   metadata is included in graph visualization/counts. The API exposes `last_synced_at`.
5. Resolve CAUSED: schema says Incident -> Service; task asks for a real PR artifact.
   An additional artifact relationship requires a contract definition.
6. Resolve synthetic flags: the task requires every synthetic-layer edge to be true;
   schema says RESOLVED_BY to a real merged PR and CITES to real PRs are false.
   These fabricated incident/decision relationships must not imply real historical causation.
7. Define Decision -> Doc CITES, absent from the edge table.
8. Confirm local JSON source_url values for synthetic nodes; per-label schema tables
   currently specify `synthetic`, while the task requests `ingest/data/*.json`.

The existing ingest README also requests persistence through graph write primitives;
none exist in this checkout. The new task asks for parameterized UNWIND loaders and
index creation. Please clarify whether ingest may own those writes or provide a graph
writer import interface. Index execution currently belongs to graph per schema.md.

Independent work completed: `python -m ingest.github_loader` collects cached raw JSON,
including commit files, PR files, issue timelines and labels, contributors, Markdown
blobs and CODEOWNERS. `GitHub.updated(since)` fetches updated issue and PR data with
fresh detail/files/timelines. It does not yet persist a graph watermark.

Live collection currently fails with HTTP 401 for the configured GITHUB_TOKEN.
Replace that value locally; do not send or commit credentials. Cache stays ignored.

Validation: `python -m pytest tests/ingest -q` (five passing tests).

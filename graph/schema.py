"""Idempotent contract indexes and native FalkorDB UNIQUE constraints."""

import logging
from threading import Lock
from time import monotonic, sleep

logger = logging.getLogger(__name__)

INDEXES = (
    ("Commit", "id", "CREATE INDEX FOR (n:Commit) ON (n.id)"),
    ("SyncMeta", "id", "CREATE INDEX FOR (n:SyncMeta) ON (n.id)"),
    ("Commit", "sha", "CREATE INDEX FOR (n:Commit) ON (n.sha)"),
    ("Service", "id", "CREATE INDEX FOR (n:Service) ON (n.id)"),
    ("Person", "id", "CREATE INDEX FOR (n:Person) ON (n.id)"),
    ("Team", "id", "CREATE INDEX FOR (n:Team) ON (n.id)"),
    ("Repo", "id", "CREATE INDEX FOR (n:Repo) ON (n.id)"),
    ("File", "id", "CREATE INDEX FOR (n:File) ON (n.id)"),
    ("PR", "id", "CREATE INDEX FOR (n:PR) ON (n.id)"),
    ("Issue", "id", "CREATE INDEX FOR (n:Issue) ON (n.id)"),
    ("Incident", "id", "CREATE INDEX FOR (n:Incident) ON (n.id)"),
    ("Decision", "id", "CREATE INDEX FOR (n:Decision) ON (n.id)"),
    ("Doc", "id", "CREATE INDEX FOR (n:Doc) ON (n.id)"),
    ("Service", "name", "CREATE INDEX FOR (n:Service) ON (n.name)"),
    ("Person", "github_login", "CREATE INDEX FOR (n:Person) ON (n.github_login)"),
)
INDEX_LIST = "CALL db.indexes() YIELD label, properties RETURN label, properties"
CONSTRAINT_LIST = "CALL db.constraints()"
_lock = Lock()


def ensure_schema(graph):
    """Check metadata before DDL; fail on invalid or non-operational constraints."""
    with _lock:
        existing = {
            (label, prop)
            for label, props in graph.query(INDEX_LIST, {}).result_set
            for prop in props
        }
        for label, prop, query in INDEXES:
            if (label, prop) not in existing:
                graph.query(query, {})
        constraints = graph.query(CONSTRAINT_LIST, {}).result_set
        existing_constraints = {
            (r[1], tuple(r[2])) for r in constraints if r[0] == "UNIQUE" and r[3] == "NODE"
        }
        expected = {(label, (prop,)) for label, prop, _ in INDEXES if prop == "id"}
        for label, props in sorted(expected - existing_constraints):
            # GRAPH.CONSTRAINT is a Redis command, not interpolated Cypher.
            graph.execute_command(
                "GRAPH.CONSTRAINT",
                "CREATE",
                graph.name,
                "UNIQUE",
                "NODE",
                label,
                "PROPERTIES",
                1,
                *props,
            )
        deadline = monotonic() + 5
        while True:
            constraints = graph.query(CONSTRAINT_LIST, {}).result_set
            statuses = [
                r[4]
                for r in constraints
                if (r[1], tuple(r[2])) in expected and r[0] == "UNIQUE" and r[3] == "NODE"
            ]
            if "FAILED" in statuses:
                raise RuntimeError("graph uniqueness constraint failed; resolve duplicate IDs")
            if len(statuses) == len(expected) and all(s == "OPERATIONAL" for s in statuses):
                return
            if monotonic() > deadline:
                # Indexes are already created above (point lookups stay fast either way),
                # and every write goes through graph/writer.py's MERGE-on-id, which stays
                # correct without the uniqueness constraint - it just won't reject a
                # concurrent duplicate-id write as fast as a native constraint would.
                # FalkorDB Cloud has been observed to leave constraints PENDING well past
                # this deadline, so don't block startup/ingest on them; warn and continue.
                pending = len(expected) - len(statuses)
                logger.warning(
                    "graph uniqueness constraints did not become operational within 5s "
                    "(%d pending/missing of %d); continuing without them - writes stay "
                    "idempotent via MERGE on id",
                    pending,
                    len(expected),
                )
                return
            sleep(0.02)

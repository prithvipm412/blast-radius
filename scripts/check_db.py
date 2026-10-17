#!/usr/bin/env python3
"""Connect to FalkorDB using .env, run a smoke test, print OK."""

import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

try:
    from falkordb import FalkorDB
except ImportError:
    print("FAIL: `falkordb` package not installed. Run `pip install -e .` or `pip install -r requirements.txt`.")
    sys.exit(1)


def main() -> None:
    host = os.environ.get("FALKORDB_HOST", "localhost")
    port = int(os.environ.get("FALKORDB_PORT", "6379"))
    username = os.environ.get("FALKORDB_USERNAME") or None
    password = os.environ.get("FALKORDB_PASSWORD") or None
    graph_name = os.environ.get("FALKORDB_GRAPH", "blast_radius")

    try:
        db = FalkorDB(host=host, port=port, username=username, password=password)
        graph = db.select_graph(graph_name)

        result = graph.query("RETURN 1 AS one")
        assert result.result_set[0][0] == 1, "RETURN 1 did not return 1"

        test_id = f"check_db:{uuid.uuid4()}"
        graph.query(
            "CREATE (n:CheckDbTest {id: $id}) RETURN n.id",
            {"id": test_id},
        )
        found = graph.query(
            "MATCH (n:CheckDbTest {id: $id}) RETURN n.id",
            {"id": test_id},
        )
        assert found.result_set and found.result_set[0][0] == test_id, "test node not found after create"

        graph.query(
            "MATCH (n:CheckDbTest {id: $id}) DELETE n",
            {"id": test_id},
        )
        gone = graph.query(
            "MATCH (n:CheckDbTest {id: $id}) RETURN n",
            {"id": test_id},
        )
        assert not gone.result_set, "test node still present after delete"

    except Exception as exc:  # noqa: BLE001 - this is a CLI smoke test, report and exit non-zero
        print(f"FAIL: {exc}")
        sys.exit(1)

    print("OK")


if __name__ == "__main__":
    main()

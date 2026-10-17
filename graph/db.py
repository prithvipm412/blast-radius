"""Shared lazy FalkorDB connection; importing tools never opens a connection."""

import os
from functools import lru_cache
from threading import Lock

from dotenv import load_dotenv
from falkordb import FalkorDB

load_dotenv()
_lock = Lock()
_client = None


def get_client() -> FalkorDB:
    """One connection pool per process, configured by FALKORDB_* in .env."""
    global _client
    with _lock:
        if _client is None:
            _client = FalkorDB(
                host=os.getenv("FALKORDB_HOST", "localhost"),
                port=int(os.getenv("FALKORDB_PORT", "6379")),
                username=os.getenv("FALKORDB_USERNAME") or None,
                password=os.getenv("FALKORDB_PASSWORD") or None,
                socket_connect_timeout=5,
                socket_timeout=10,
            )
    return _client


@lru_cache(maxsize=8)
def _select_graph(name):
    from graph.schema import ensure_schema

    graph = get_client().select_graph(name)
    ensure_schema(graph)
    return graph


def get_graph(name: str | None = None):
    """Select an explicit graph, or FALKORDB_GRAPH (default blast_radius)."""
    return _select_graph(name or os.getenv("FALKORDB_GRAPH", "blast_radius"))

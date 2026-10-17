"""FastAPI app implementing contracts/api.md.

Run: uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

load_dotenv()

from agent.loop import run_alert, run_ask  # noqa: E402 - must follow load_dotenv()
from agent.registry import graph_neighborhood, graph_stats  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Blast Radius API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"service": "blast-radius-api", "status": "ok"}


class AskRequest(BaseModel):
    question: str
    mode: str = "graph"


class AlertRequest(BaseModel):
    service: str


class SyncRequest(BaseModel):
    pass


def _sse_stream(events) -> EventSourceResponse:
    def event_stream():
        for event in events:
            yield json.dumps(event)

    return EventSourceResponse(event_stream())


@app.post("/api/ask")
async def ask(req: AskRequest):
    return _sse_stream(run_ask(req.question, req.mode))


@app.post("/api/alert")
async def alert(req: AlertRequest):
    return _sse_stream(run_alert(req.service))


@app.get("/api/graph")
async def get_graph(focus: str | None = None, depth: int = 2):
    try:
        return graph_neighborhood(focus=focus, depth=depth)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/stats")
async def get_stats():
    return graph_stats()


@app.post("/api/sync")
async def sync(req: SyncRequest | None = None):
    try:
        from ingest.sync import sync as ingest_sync
    except ImportError as exc:
        raise HTTPException(status_code=501, detail="ingest.sync not implemented yet") from exc

    started_at = datetime.now(timezone.utc)
    ingest_sync()
    finished_at = datetime.now(timezone.utc)
    return {"status": "ok", "started_at": started_at.isoformat(), "finished_at": finished_at.isoformat()}

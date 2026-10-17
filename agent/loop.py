"""The agent loop.

Two entrypoints, each a generator yielding events in the exact shape defined
by contracts/api.md ({"type": "tool_call"|"tool_result"|"answer"|"error", ...}):

- run_ask(question, mode): free-form Q&A for POST /api/ask. mode="graph" drives
  an LLM tool-calling loop (max MAX_TOOL_STEPS) against agent.registry's tools.
  mode="rag" bypasses tools entirely and delegates to agent.rag_baseline.
- run_alert(service): the canned investigation playbook for POST /api/alert.

api/main.py imports these generators directly and streams their yields as SSE.
"""

from __future__ import annotations

import json
import logging
from typing import Generator

from agent.llm import Message, get_provider
from agent.registry import TOOL_REGISTRY, TOOL_SCHEMAS

logger = logging.getLogger(__name__)

MAX_TOOL_STEPS = 8

SYSTEM_PROMPT = """You are Blast Radius, an on-call agent with a company brain backed by a knowledge graph (FalkorDB).

Rules:
- Always ground your answers in the results of the tools you call. Never invent people, services, incidents, decisions, or PRs that did not come back from a tool call.
- Every factual claim must be traceable to a `source_url` field from a tool result. When you state a fact, say what it's based on (e.g. "per PR #234" or "per the cartservice runbook").
- If the tools don't have the information needed to answer, say so plainly rather than guessing.
- Prefer calling a tool over speculating whenever the question is about services, ownership, incidents, or decisions.
- Be concise. This is an on-call context: the reader wants the answer fast, with evidence, not a lecture.
"""

ALERT_PLAYBOOK = ["blast_radius", "find_owners", "find_experts", "similar_incidents", "trace_decision"]


def _run_tool(name: str, args: dict) -> dict:
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        raise ValueError(f"unknown tool: {name}")
    return fn(**args)


def run_ask(question: str, mode: str = "graph") -> Generator[dict, None, None]:
    if mode == "rag":
        from agent.rag_baseline import answer_question

        try:
            text = answer_question(question)
        except Exception as exc:  # noqa: BLE001 - surface as a terminal SSE error event
            yield {"type": "error", "message": str(exc)}
            return
        yield {"type": "answer", "text": text, "done": True}
        return

    if mode != "graph":
        yield {"type": "error", "message": f"unknown mode: {mode!r} (expected 'graph' or 'rag')"}
        return

    try:
        provider = get_provider()
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": f"LLM provider error: {exc}"}
        return

    messages: list[Message] = [Message(role="user", content=question)]
    last_text = ""

    for _ in range(MAX_TOOL_STEPS):
        try:
            response = provider.generate(SYSTEM_PROMPT, messages, TOOL_SCHEMAS)
        except Exception as exc:  # noqa: BLE001
            yield {"type": "error", "message": f"LLM error: {exc}"}
            return

        last_text = response.text

        if not response.tool_calls:
            yield {"type": "answer", "text": response.text, "done": True}
            return

        messages.append(Message(role="assistant", content=response.text, tool_calls=response.tool_calls))

        for tc in response.tool_calls:
            yield {"type": "tool_call", "tool": tc.name, "args": tc.args}
            try:
                result = _run_tool(tc.name, tc.args)
            except Exception as exc:  # noqa: BLE001
                yield {"type": "error", "message": str(exc)}
                return
            yield {"type": "tool_result", "tool": tc.name, "result": result}
            messages.append(
                Message(role="tool", content=json.dumps(result, default=str), tool_call_id=tc.id, name=tc.name)
            )

    yield {
        "type": "answer",
        "text": (
            "I wasn't able to reach a grounded answer within the allotted tool-call budget "
            f"({MAX_TOOL_STEPS} steps). Here's my last partial reasoning: " + (last_text or "(no text produced)")
        ),
        "done": True,
    }


def run_alert(service: str) -> Generator[dict, None, None]:
    results: dict[str, dict] = {}

    for tool_name in ALERT_PLAYBOOK:
        args = {"service": service}
        yield {"type": "tool_call", "tool": tool_name, "args": args}
        try:
            result = _run_tool(tool_name, args)
        except Exception as exc:  # noqa: BLE001
            yield {"type": "error", "message": str(exc)}
            return
        yield {"type": "tool_result", "tool": tool_name, "result": result}
        results[tool_name] = result

    try:
        provider = get_provider()
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": f"LLM provider error: {exc}"}
        return

    synthesis_prompt = (
        f"An alert just fired on service '{service}'. Using ONLY the tool results below, draft a concise "
        "incident note in markdown: what breaks (blast radius), who owns it, who the relevant experts are, "
        "similar past incidents, and relevant architectural decisions. Cite source_url for every claim you can. "
        "If a section has no data, say so explicitly rather than inventing it.\n\n"
        f"Tool results:\n{json.dumps(results, indent=2, default=str)}"
    )
    try:
        response = provider.generate(SYSTEM_PROMPT, [Message(role="user", content=synthesis_prompt)], tools=[])
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": f"LLM error: {exc}"}
        return

    note_text = response.text

    issue_args = {"service": service, "summary": note_text, "dry_run": True}
    yield {"type": "tool_call", "tool": "create_incident_issue", "args": issue_args}
    try:
        issue_result = _run_tool("create_incident_issue", issue_args)
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": str(exc)}
        return
    yield {"type": "tool_result", "tool": "create_incident_issue", "result": issue_result}

    yield {"type": "answer", "text": note_text, "done": True}

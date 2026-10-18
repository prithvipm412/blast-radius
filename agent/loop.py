"""The agent loop.

Two entrypoints, each a generator yielding events in the exact shape defined
by contracts/api.md ({"type": "tool_call"|"tool_result"|"answer"|"error", ...}):

- run_ask(question, mode): free-form Q&A for POST /api/ask. mode="graph" drives
  an LLM tool-calling loop (max MAX_TOOL_STEPS) against agent.registry's tools.
  mode="rag" bypasses tools entirely and delegates to agent.rag_baseline. If the
  LLM itself is unavailable (provider construction or any generate() call
  fails, for any reason), falls back to _ask_fallback() instead of erroring.
- run_alert(service): the canned investigation playbook for POST /api/alert.
  This is fully deterministic and LLM-independent: the playbook tools always
  run in a fixed order, the answer is built from their results with a markdown
  template (agent.templates), and an LLM polish pass is only ever an optional,
  best-effort cosmetic step on top (see _try_polish) — it can fail for any
  reason without affecting the investigation or surfacing an error.

Tool execution errors (e.g. "unknown service") are real errors and are still
surfaced as a terminal {"type": "error", ...} event in both entrypoints — only
LLM failures are treated as non-fatal and silently routed around.

api/main.py imports these generators directly and streams their yields as SSE.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Generator

from agent.llm import Message, get_provider
from agent.registry import TOOL_REGISTRY, TOOL_SCHEMAS
from agent.templates import build_ask_fallback_markdown, build_investigation_markdown, render_tool_section

logger = logging.getLogger(__name__)

MAX_TOOL_STEPS = 8

# Hard cap on the optional alert-answer polish LLM call. Anything slower than a
# demo-reasonable wait (slow cold model, provider hiccup) is treated the same
# as an outright error: drop it and keep the deterministic template.
POLISH_TIMEOUT_SECONDS = 15

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
    except Exception as exc:  # noqa: BLE001 - no LLM available at all: fall back, don't error
        logger.warning("LLM provider unavailable for /api/ask (%s); falling back to direct tool lookup", exc)
        yield from _ask_fallback(question)
        return

    messages: list[Message] = [Message(role="user", content=question)]
    last_text = ""

    for _ in range(MAX_TOOL_STEPS):
        try:
            response = provider.generate(SYSTEM_PROMPT, messages, TOOL_SCHEMAS)
        except Exception as exc:  # noqa: BLE001 - LLM call failed: fall back, don't error
            logger.warning("LLM call failed mid-/api/ask (%s); falling back to direct tool lookup", exc)
            yield from _ask_fallback(question)
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


# Keyword pattern -> tool name, used only when the LLM is unavailable and we
# need a cheap heuristic for "the most relevant tool(s)" for a free-text
# question. Each pattern is matched with \b word boundaries (not bare
# substring) so e.g. "own" doesn't spuriously match inside "down"/"known"/
# "shown". Order matters: earlier matches come first in the rendered answer.
_NO_SERVICE_TOOLS = {"critical_services", "single_points_of_failure", "team_clusters"}
_FALLBACK_KEYWORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bbreaks?\b|\bdown\b|\bdepend(s|ency|encies)?\b|\baffects?\b", re.I), "blast_radius"),
    (re.compile(r"\bowners?\b|\bowns?\b|\bownership\b", re.I), "find_owners"),
    (re.compile(r"\bexperts?\b|\bcontribut\w*\b", re.I), "find_experts"),
    (re.compile(r"\bincidents?\b|\boutages?\b|\bsimilar\b", re.I), "similar_incidents"),
    (re.compile(r"\bdecisions?\b|\barchitect\w*\b", re.I), "trace_decision"),
    (re.compile(r"\bcritical\b", re.I), "critical_services"),
    (re.compile(r"\bsingle point\w*\b", re.I), "single_points_of_failure"),
    (re.compile(r"\bclusters?\b", re.I), "team_clusters"),
]


def _pick_fallback_tools(question: str, service: str | None) -> list[tuple[str, dict]]:
    picks: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for pattern, tool_name in _FALLBACK_KEYWORDS:
        if tool_name in seen or not pattern.search(question):
            continue
        if tool_name in _NO_SERVICE_TOOLS:
            picks.append((tool_name, {}))
        elif service:
            picks.append((tool_name, {"service": service}))
        else:
            continue
        seen.add(tool_name)
    if not picks and service:
        picks.append(("blast_radius", {"service": service}))
    return picks


def _ask_fallback(question: str) -> Generator[dict, None, None]:
    """Deterministic, LLM-free degraded mode for /api/ask: resolve a mentioned
    service (if any) via search_entities, run whatever tool(s) the question's
    keywords suggest are most relevant, and render a template answer from
    their results. Streams the same tool_call/tool_result events as the normal
    path so the UI is unchanged; never yields an {"type": "error"} event for
    the LLM failure that triggered this path."""
    service: str | None = None
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", question):
        args = {"text": token}
        try:
            result = _run_tool("search_entities", args)
        except Exception:  # noqa: BLE001 - fallback path, keep trying other tokens
            continue
        service_match = next((m for m in result["data"]["matches"] if m["label"] == "Service"), None)
        if service_match:
            yield {"type": "tool_call", "tool": "search_entities", "args": args}
            yield {"type": "tool_result", "tool": "search_entities", "result": result}
            service = service_match["id"]
            break

    ran: list[tuple[str, dict]] = []
    for tool_name, args in _pick_fallback_tools(question, service):
        yield {"type": "tool_call", "tool": tool_name, "args": args}
        try:
            result = _run_tool(tool_name, args)
        except Exception as exc:  # noqa: BLE001 - a real tool error, not an LLM failure: surface it
            yield {"type": "error", "message": str(exc)}
            return
        yield {"type": "tool_result", "tool": tool_name, "result": result}
        ran.append((tool_name, result))

    yield {"type": "answer", "text": build_ask_fallback_markdown(ran), "done": True}


def _try_polish(template_text: str) -> str:
    """Try one LLM call to polish the deterministic alert template into more
    natural prose, preserving every fact. On ANY failure - missing/invalid API
    key, 429, 400, 401, timeout, or anything else - silently keep the template
    unchanged. Never raises and never produces an {"type": "error"} event:
    alerts must complete on tool results alone."""
    try:
        provider = get_provider()
    except Exception as exc:  # noqa: BLE001
        logger.info("alert polish skipped, no LLM provider available (%s)", exc)
        return template_text

    polish_prompt = (
        "Rewrite the following incident note to read naturally and concisely, as prose, "
        "while preserving every fact, id, and citation exactly as given. Do not invent, "
        "remove, or change any fact, number, name, or id, and keep the same section "
        "structure and headings.\n\n" + template_text
    )

    def call():
        return provider.generate(SYSTEM_PROMPT, [Message(role="user", content=polish_prompt)], [])

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(call)
        response = future.result(timeout=POLISH_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - any LLM failure (incl. timeout) keeps the template
        logger.info("alert polish LLM call failed (%s); keeping deterministic template", exc)
        return template_text
    finally:
        # wait=False: don't block the request on a hung call past the timeout above.
        pool.shutdown(wait=False)

    polished = (response.text or "").strip()
    return polished or template_text


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

    # Deterministic, LLM-independent from here on: the investigation note is built
    # straight from the 5 tool results above, used verbatim as the draft issue's
    # summary, then rendered into the final answer alongside the issue section.
    investigation_md = build_investigation_markdown(service, results)

    issue_args = {"service": service, "summary": investigation_md, "dry_run": True}
    yield {"type": "tool_call", "tool": "create_incident_issue", "args": issue_args}
    try:
        issue_result = _run_tool("create_incident_issue", issue_args)
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": str(exc)}
        return
    yield {"type": "tool_result", "tool": "create_incident_issue", "result": issue_result}

    template_text = investigation_md + "\n\n" + render_tool_section("create_incident_issue", issue_result)

    # Optional cosmetic polish only - see _try_polish's docstring. Any LLM problem
    # (missing/invalid key, 429, 400, 401, timeout) silently keeps template_text.
    final_text = _try_polish(template_text)

    yield {"type": "answer", "text": final_text, "done": True}

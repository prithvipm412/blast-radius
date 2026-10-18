"""Regression tests for agent/loop.py's LLM-independence guarantees.

/api/alert must always complete with a grounded answer built from tool
results, and /api/ask must degrade to a direct tool lookup, in both cases
regardless of why the LLM is unavailable (missing key, 429, 400, timeout,
anything). These tests force that failure deterministically by monkeypatching
agent.loop.get_provider, rather than relying on a real provider outage.

Uses the stub tool backend (tests/fixtures/sample_graph.json) so these tests
never touch a real FalkorDB or LLM provider.
"""

from __future__ import annotations

import os

os.environ.setdefault("TOOL_BACKEND", "stub")

import pytest

import agent.loop as loop


class _AlwaysFails:
    def generate(self, *args, **kwargs):
        raise RuntimeError("simulated LLM outage")


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    monkeypatch.setattr(loop, "get_provider", lambda: (_ for _ in ()).throw(RuntimeError("no provider")))


def test_run_alert_completes_without_llm():
    events = list(loop.run_alert("cartservice"))

    assert not any(e["type"] == "error" for e in events)
    assert events[-1]["type"] == "answer" and events[-1]["done"] is True

    tool_calls = [e["tool"] for e in events if e["type"] == "tool_call"]
    assert tool_calls == [*loop.ALERT_PLAYBOOK, "create_incident_issue"]

    text = events[-1]["text"]
    for heading in ("Blast radius", "Owners", "Experts", "Similar incidents", "Architectural decision", "Drafted issue"):
        assert f"### {heading}" in text


def test_run_alert_still_errors_on_bad_service():
    events = list(loop.run_alert("svc:does-not-exist"))
    assert events[-1]["type"] == "error"


def test_run_ask_falls_back_without_llm():
    events = list(loop.run_ask("What breaks if cartservice goes down?", mode="graph"))

    assert not any(e["type"] == "error" for e in events)
    assert events[-1]["type"] == "answer" and events[-1]["done"] is True

    tool_calls = [e["tool"] for e in events if e["type"] == "tool_call"]
    assert "blast_radius" in tool_calls
    assert "LLM unavailable" in events[-1]["text"]


def test_run_ask_fallback_has_no_entity_match():
    events = list(loop.run_ask("asdkjqwelkxzcv nonsense gibberish", mode="graph"))

    assert not any(e["type"] == "error" for e in events)
    assert events[-1]["type"] == "answer"
    assert "couldn't resolve" in events[-1]["text"]


@pytest.mark.parametrize(
    "question,expected_tool",
    [
        ("Who owns cartservice?", "find_owners"),
        ("What breaks if cartservice goes down?", "blast_radius"),
        ("Who are the experts on cartservice?", "find_experts"),
    ],
)
def test_fallback_tool_selection_keywords(question, expected_tool):
    picks = loop._pick_fallback_tools(question, "svc:cartservice")
    assert expected_tool in [name for name, _ in picks]


def test_fallback_does_not_false_positive_on_own_substring():
    # "down" contains "own" as a substring - must not spuriously pick find_owners.
    picks = loop._pick_fallback_tools("what goes down if cartservice fails", "svc:cartservice")
    assert "find_owners" not in [name for name, _ in picks]


def test_groq_tool_choice_is_never_an_object(monkeypatch):
    from agent.llm import GroqProvider, Message

    captured = {}

    class _FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)

            class _Choice:
                class message:
                    content = "ok"
                    tool_calls = None

            class _Response:
                choices = [_Choice()]

            return _Response()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    provider = GroqProvider.__new__(GroqProvider)
    provider.api_key = "test"
    provider.model = "llama-3.3-70b-versatile"
    provider.client = _FakeClient()

    provider.generate("system", [Message(role="user", content="hi")], [{"name": "t", "parameters": {"type": "object", "properties": {}}}])
    assert captured["tool_choice"] == "auto"

    provider.generate("system", [Message(role="user", content="hi")], [])
    assert captured["tool_choice"] is None

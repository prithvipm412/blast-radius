"""LLM provider abstraction.

LLM_PROVIDER in .env picks the primary provider: "gemini" (default) or "groq".
Gemini uses the `google-genai` SDK with native function calling. Groq is the
OpenAI-compatible fallback. Both are wrapped behind the same `LLMProvider`
interface so agent/loop.py and agent/rag_baseline.py never branch on provider.

Retry: each provider call is retried with exponential backoff on a 429 (rate
limit). If LLM_PROVIDER=gemini and GROQ_API_KEY is set, repeated 429s from
Gemini (retries exhausted) automatically fall over to Groq for the rest of
that call via get_provider()'s FallbackProvider wrapper.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class RateLimitError(LLMError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]
    # Provider-specific opaque pass-through data (e.g. Gemini's thought_signature,
    # required on replay for multi-turn function calling). Ignored by other providers.
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    role: str  # "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None  # set on role="tool" messages
    name: str | None = None  # tool name, set on role="tool" messages


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider:
    name = "base"

    def generate(self, system: str, messages: list[Message], tools: list[dict]) -> LLMResponse:
        raise NotImplementedError


def _retry_with_backoff(fn, *, max_retries: int = 4, base_delay: float = 1.0):
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except RateLimitError as exc:
            last_exc = exc
            if attempt == max_retries:
                raise
            delay = base_delay * (2**attempt)
            logger.warning(
                "rate limited (%s), retrying in %.1fs (attempt %d/%d)",
                exc,
                delay,
                attempt + 1,
                max_retries,
            )
            time.sleep(delay)
    raise last_exc  # pragma: no cover - unreachable, loop always returns or raises


def _is_rate_limit(exc: Exception) -> bool:
    try:
        import groq

        if isinstance(exc, groq.RateLimitError):
            return True
    except ImportError:
        pass
    try:
        from google.genai import errors as genai_errors

        if isinstance(exc, genai_errors.APIError) and getattr(exc, "code", None) == 429:
            return True
    except ImportError:
        pass
    return False


# --- Gemini --------------------------------------------------------------


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        from google import genai

        self.api_key = api_key or os.environ["GEMINI_API_KEY"]
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
        self.client = genai.Client(api_key=self.api_key)

    def generate(self, system: str, messages: list[Message], tools: list[dict]) -> LLMResponse:
        from google.genai import types

        contents = _messages_to_gemini_contents(messages, types)
        genai_tools = None
        if tools:
            declarations = [
                types.FunctionDeclaration(
                    name=t["name"],
                    description=t.get("description", ""),
                    parameters_json_schema=t["parameters"],
                )
                for t in tools
            ]
            genai_tools = [types.Tool(function_declarations=declarations)]

        config = types.GenerateContentConfig(system_instruction=system, tools=genai_tools)

        def call():
            try:
                return self.client.models.generate_content(model=self.model, contents=contents, config=config)
            except Exception as exc:  # noqa: BLE001 - re-raised as RateLimitError or propagated as-is
                if _is_rate_limit(exc):
                    raise RateLimitError(str(exc)) from exc
                raise

        response = _retry_with_backoff(call)
        return _gemini_response_to_llmresponse(response)


def _messages_to_gemini_contents(messages: list[Message], types) -> list:
    contents = []
    for m in messages:
        if m.role == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=m.content)]))
        elif m.role == "assistant":
            parts = []
            if m.content:
                parts.append(types.Part(text=m.content))
            for tc in m.tool_calls:
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(id=tc.id, name=tc.name, args=tc.args),
                        thought_signature=tc.extra.get("thought_signature"),
                    )
                )
            contents.append(types.Content(role="model", parts=parts))
        elif m.role == "tool":
            try:
                response_payload = json.loads(m.content)
            except (TypeError, json.JSONDecodeError):
                response_payload = {"result": m.content}
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(name=m.name, response=response_payload)],
                )
            )
    return contents


def _gemini_response_to_llmresponse(response) -> LLMResponse:
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        content = candidates[0].content
        for part in (content.parts if content and content.parts else []):
            if getattr(part, "text", None):
                text_parts.append(part.text)
            fc = getattr(part, "function_call", None)
            if fc is not None:
                thought_signature = getattr(part, "thought_signature", None)
                extra = {"thought_signature": thought_signature} if thought_signature else {}
                tool_calls.append(
                    ToolCall(id=fc.id or str(uuid.uuid4()), name=fc.name, args=dict(fc.args or {}), extra=extra)
                )
    return LLMResponse(text="".join(text_parts), tool_calls=tool_calls)


# --- Groq ------------------------------------------------------------------


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        from groq import Groq

        self.api_key = api_key or os.environ["GROQ_API_KEY"]
        self.model = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        # max_retries=0: our own _retry_with_backoff owns retry/backoff behavior.
        self.client = Groq(api_key=self.api_key, max_retries=0)

    def generate(self, system: str, messages: list[Message], tools: list[dict]) -> LLMResponse:
        groq_messages = _messages_to_openai(system, messages)
        groq_tools = [_tool_schema_to_openai(t) for t in tools] if tools else None

        def call():
            try:
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=groq_messages,
                    tools=groq_tools,
                    tool_choice="auto" if groq_tools else None,
                )
            except Exception as exc:  # noqa: BLE001
                if _is_rate_limit(exc):
                    raise RateLimitError(str(exc)) from exc
                raise

        response = _retry_with_backoff(call)
        return _openai_response_to_llmresponse(response)


def _tool_schema_to_openai(t: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t["parameters"],
        },
    }


def _messages_to_openai(system: str, messages: list[Message]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]
    for m in messages:
        if m.role == "user":
            out.append({"role": "user", "content": m.content})
        elif m.role == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": m.content or None}
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.args)},
                    }
                    for tc in m.tool_calls
                ]
            out.append(msg)
        elif m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
    return out


def _openai_response_to_llmresponse(response) -> LLMResponse:
    message = response.choices[0].message
    tool_calls = [
        ToolCall(id=tc.id, name=tc.function.name, args=json.loads(tc.function.arguments))
        for tc in (message.tool_calls or [])
    ]
    return LLMResponse(text=message.content or "", tool_calls=tool_calls)


# --- Fallback wiring ---------------------------------------------------------


class FallbackProvider(LLMProvider):
    """Wraps a primary provider; on repeated 429s (RateLimitError, retries exhausted)
    from the primary, retries the same call once against the fallback provider."""

    def __init__(self, primary: LLMProvider, fallback: LLMProvider):
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name

    def generate(self, system: str, messages: list[Message], tools: list[dict]) -> LLMResponse:
        try:
            return self.primary.generate(system, messages, tools)
        except RateLimitError:
            logger.warning("falling back from %s to %s after repeated 429s", self.primary.name, self.fallback.name)
            return self.fallback.generate(system, messages, tools)


def get_provider() -> LLMProvider:
    provider_name = os.environ.get("LLM_PROVIDER", "gemini").lower()
    if provider_name == "groq":
        return GroqProvider()
    if provider_name != "gemini":
        raise LLMError(f"unknown LLM_PROVIDER: {provider_name!r} (expected 'gemini' or 'groq')")

    gemini = GeminiProvider()
    if os.environ.get("GROQ_API_KEY"):
        return FallbackProvider(gemini, GroqProvider())
    return gemini

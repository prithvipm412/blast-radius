# agent/ — owner: lead

Not built yet — next task after this skeleton. Will contain:

- Provider abstraction: `LLM_PROVIDER=gemini|groq` in `.env`. Gemini via `google-genai` SDK with native function calling; Groq (OpenAI-compatible tool calling) as fallback.
- The agentic loop: takes a question, exposes every function in `contracts/tools.md` (via `graph.tools`) as an LLM tool, runs the call/result loop, yields events matching `contracts/api.md`'s SSE shape (`tool_call`, `tool_result`, `answer`, `error`) so `api/` can stream them directly.
- The canned "alert investigation" flow for `POST /api/alert` (blast radius → owners → experts → similar incidents → decisions → draft note).

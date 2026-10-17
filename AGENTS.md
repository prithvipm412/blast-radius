# AGENTS.md — rules for everyone working on Blast Radius

This repo is being built by multiple agents in parallel, each in their own git worktree. These rules exist so three people's work merges without conflict. Read this before touching anything.

## Ownership

| folder | owner |
|---|---|
| `contracts/` | lead only. **Never edit.** If a contract seems wrong or missing something you need, stop and ask the human to relay the change request to the lead. Don't work around it by inventing your own shape — that breaks the other two agents. |
| `agent/` | lead |
| `api/` | lead |
| `ingest/` | Codex 1 |
| `graph/` | Codex 2 |
| `web/` | Codex 3 |
| `scripts/`, `docs/`, `tests/` | shared — add files relevant to your own folder here freely (e.g. `tests/test_graph_tools.py` if you're Codex 2), but don't rewrite another agent's test files or scripts. |

Stay inside your folder. If you think you need to touch someone else's folder, you've probably found a contract gap — ask the human to relay it to the lead instead of patching around it.

## Hard rules

1. **Read `contracts/` first**, every session, before writing code. `schema.md`, `tools.md`, `api.md` are the ground truth for node/edge shapes, function signatures, and HTTP/SSE shapes. Code that doesn't match them will not integrate.
2. **Never edit `contracts/`.** Not even typo fixes. Flag it to the human instead.
3. **Never commit `.env`.** It's gitignored — don't force-add it, don't paste its contents into code or commit messages. Use `.env.example` as the template for what variables exist.
4. **All Cypher must be parameterized.** Use `$param` placeholders and pass a params dict to the FalkorDB client — never f-string or `.format()` a value into a Cypher query body. This applies to every write and read, no exceptions (SQL/Cypher-injection risk, and it's also just correct practice).
5. **Commit small and often**, with clear messages describing what changed and why (not "wip" or "fix"). Small commits merge cleanly across worktrees; one giant commit at the end does not.
6. **Match the contracts' return shapes exactly**, including field names and the `{"data", "cypher", "params", "path"}` envelope for every graph tool (see `contracts/tools.md`). The frontend and agent loop are built against these shapes verbatim.
7. **Don't introduce new top-level dependencies** without checking `pyproject.toml`/`requirements.txt` (Python) or `web/package.json` (frontend) for what's already there — prefer what's already pinned.
8. **Synthetic vs. real data must be labeled correctly.** Every node/edge needs an accurate `synthetic` bool per `contracts/schema.md`'s reference table. This isn't cosmetic — the product's pitch depends on being honest about what's real GitHub data vs. fabricated demo data.

## When you're blocked

If a contract is ambiguous, incomplete, or you've hit something it doesn't cover: stop, write down exactly what you need, and ask the human to relay it to the lead. Don't guess and don't block on it silently — work around the gap with a clearly-marked TODO/stub if you can keep moving on something else in your folder meanwhile.

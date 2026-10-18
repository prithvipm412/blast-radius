"""Deterministic markdown rendering of tool results.

Used by agent/loop.py so /api/alert (and the /api/ask LLM-failure fallback) can
produce a complete, readable answer straight from tool results, with no LLM
call required. Keeping this separate from loop.py keeps the control flow
(which tools run, in what order, optional LLM polish) readable on its own.
"""

from __future__ import annotations

import json


def _bulleted(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines) if lines else "_(none found)_"


def blast_radius_section(result: dict) -> str:
    data = result["data"]
    root = data["root"]
    affected = data["affected"]
    if not affected:
        body = f"Nothing in the graph transitively depends on `{root}` — no downstream blast radius found."
    else:
        lines = [f"`{a['id']}` ({a['depth']} hop{'s' if a['depth'] != 1 else ''} away)" for a in affected]
        body = f"If `{root}` goes down, **{len(affected)}** service(s) are transitively affected:\n{_bulleted(lines)}"
    return f"### Blast radius\n{body}\n\n_Source: `blast_radius` tool over the dependency graph._"


def owners_section(result: dict) -> str:
    data = result["data"]
    if data.get("teams"):
        groups = data["teams"]
    elif data.get("team"):
        groups = [{**data["team"], "members": data.get("members", [])}]
    else:
        groups = []

    if not groups:
        body = "No owning team found in the graph for this service."
    else:
        lines = []
        for t in groups:
            members = t.get("members") or []
            member_names = [
                f"{m['name']} (@{m['github_login']})" if m.get("github_login") else m["name"] for m in members
            ]
            member_str = ", ".join(member_names) if member_names else "no listed members"
            lines.append(f"**{t['name']}** (`{t['id']}`) — {member_str}")
        body = "\n".join(lines)
    return f"### Owners\n{body}\n\n_Source: `find_owners` tool (Team -[:OWNS]-> Service -[:MEMBER_OF]- Person)._"


def experts_section(result: dict) -> str:
    experts = result["data"].get("experts", [])
    if not experts:
        body = "No recent contributors found for this service's files."
    else:
        lines = [
            f"{e['name']} — {e['pr_count']} PR(s), last touched {e.get('last_touched', 'unknown')}" for e in experts
        ]
        body = _bulleted(lines)
    return f"### Experts\n{body}\n\n_Source: `find_experts` tool (AUTHORED PR -[:TOUCHED]-> File -[:CONTAINS]- Service)._"


def incidents_section(result: dict) -> str:
    incidents = result["data"].get("incidents", [])
    if not incidents:
        body = "No similar past incidents found for this service or its direct dependency neighbors."
    else:
        lines = [
            f"`{i['id']}` \"{i['name']}\" ({i.get('severity', 'unknown severity')}, {i['relation']}, "
            f"started {i.get('started_at', 'unknown')})"
            for i in incidents
        ]
        body = _bulleted(lines)
    return f"### Similar incidents\n{body}\n\n_Source: `similar_incidents` tool (CAUSED/AFFECTED within 1 hop)._"


def decision_section(result: dict) -> str:
    decisions = result["data"].get("decisions", [])
    if not decisions:
        body = "No architectural decisions recorded for this service."
    else:
        lines = []
        for d in decisions:
            cites = ", ".join(d.get("cites_prs") or []) or "none"
            lines.append(
                f"`{d['id']}` \"{d['name']}\" ({d.get('status', 'unknown')}, decided {d.get('decided_at', 'unknown')}) "
                f"— cites: {cites}"
            )
        body = _bulleted(lines)
    return f"### Architectural decision\n{body}\n\n_Source: `trace_decision` tool (DECIDED -> Service, CITES -> PR/Decision)._"


def issue_section(result: dict) -> str:
    data = result["data"]
    status = "dry run — not filed" if data.get("dry_run") else f"filed at {data.get('url')}"
    body = f"Drafted GitHub issue **\"{data['title']}\"** (`{data['issue_id']}`, {status})."
    return f"### Drafted issue\n{body}\n\n_Source: `create_incident_issue` tool._"


_SECTION_RENDERERS = {
    "blast_radius": blast_radius_section,
    "find_owners": owners_section,
    "find_experts": experts_section,
    "similar_incidents": incidents_section,
    "trace_decision": decision_section,
    "create_incident_issue": issue_section,
}

_GENERIC_TITLES = {
    "search_entities": "Matching entities",
    "failure_path": "Failure path",
    "critical_services": "Most critical services",
    "single_points_of_failure": "Single points of failure",
    "team_clusters": "Team clusters",
}


def render_tool_section(tool_name: str, result: dict) -> str:
    """Render one tool result as a markdown section. Falls back to a generic
    titled JSON dump for tools with no dedicated renderer (used by the /api/ask
    fallback, which may run tools outside the fixed alert playbook)."""
    renderer = _SECTION_RENDERERS.get(tool_name)
    if renderer is not None:
        return renderer(result)
    title = _GENERIC_TITLES.get(tool_name, tool_name)
    return (
        f"### {title}\n```json\n{json.dumps(result['data'], indent=2, default=str)}\n```\n\n"
        f"_Source: `{tool_name}` tool._"
    )


def build_investigation_markdown(service: str, results: dict[str, dict]) -> str:
    """The 5 alert-playbook sections (blast radius -> owners -> experts ->
    similar incidents -> decisions), with no issue section yet. Doubles as the
    `summary` passed to create_incident_issue, and as the first 5 sections of
    the final alert answer once the issue section is appended."""
    sections = [
        render_tool_section("blast_radius", results["blast_radius"]),
        render_tool_section("find_owners", results["find_owners"]),
        render_tool_section("find_experts", results["find_experts"]),
        render_tool_section("similar_incidents", results["similar_incidents"]),
        render_tool_section("trace_decision", results["trace_decision"]),
    ]
    return f"## Incident note: `{service}`\n\n" + "\n\n".join(sections)


def build_ask_fallback_markdown(ran: list[tuple[str, dict]]) -> str:
    preamble = "The reasoning LLM is unavailable right now, so here's what the graph tools found directly:"
    if not ran:
        body = "I couldn't resolve a specific entity from your question, and the LLM is unavailable, so I don't have a grounded answer to give."
        return f"## Answer (direct graph lookup — LLM unavailable)\n\n{body}"
    sections = [render_tool_section(name, result) for name, result in ran]
    return "## Answer (direct graph lookup — LLM unavailable)\n\n" + preamble + "\n\n" + "\n\n".join(sections)

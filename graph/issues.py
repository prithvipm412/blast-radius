"""Cited incident drafts, with explicit destination checks before external writes."""

import os
import re
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from graph import queries as q


def _destination():
    repo = os.getenv("GITHUB_ISSUE_REPO", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("set GITHUB_ISSUE_REPO to the owner/repo for incident issues")
    upstream = os.getenv("GITHUB_REPO", "GoogleCloudPlatform/microservices-demo")
    if repo.casefold() in {upstream.casefold(), "googlecloudplatform/microservices-demo"}:
        raise ValueError("GITHUB_ISSUE_REPO must not be the upstream source repository")
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN is required to file an incident issue")
    return repo, token


def _post_issue(repo, token, title, body):
    response = httpx.post(
        "https://api.github.com/repos/" + repo + "/issues",
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"title": title, "body": body},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    return payload["number"], payload["html_url"]


def create_issue(service, summary, dry_run):
    from graph import tools
    from graph.evidence import Evidence

    if not isinstance(dry_run, bool):
        raise TypeError("dry_run must be a boolean")
    if not summary.strip():
        raise ValueError("summary must not be empty")
    destination = _destination() if not dry_run else None
    reports = [
        tools.blast_radius(service),
        tools.find_owners(service),
        tools.find_experts(service),
        tools.similar_incidents(service),
        tools.trace_decision(service),
    ]
    service_id = tools._service_id(service)
    # Retrieve source URLs from actual nodes, preserving all investigation evidence.
    ids = sorted({n["id"] for report in reports for n in report["path"]["nodes"]})
    rows, evidence = tools._run(q.SOURCES, {"ids": ids, "limit": tools.CAP + 1})
    props = {row[0].properties["id"]: row[0].properties for row in rows}

    def cite(id_):
        node = props[id_]
        label = node["name"].replace("[", "\\[").replace("]", "\\]")
        url = node.get("source_url")
        if url and url.startswith(("https://", "http://")):
            return "[" + label + "](" + url.replace(")", "%29") + ")"
        return label + " (synthetic; no external source)"

    title = "[Blast Radius] Incident: " + props[service_id]["name"]
    body = ["# " + title, summary, "Service: " + cite(service_id), "## Blast radius"]
    body += [
        "- " + cite(n["id"]) + " — " + str(n["depth"]) + " hop(s)"
        for n in reports[0]["data"]["affected"]
    ] or ["No downstream callers found."]
    body.append("## Owners")
    owner = reports[1]["data"]
    body.append(cite(owner["team"]["id"]) if owner["team"] else "No owner recorded.")
    body += ["- " + cite(n["id"]) for n in owner["members"]]
    body.append("## Experts (last 180 days)")
    body += [
        "- " + cite(n["id"]) + " — " + str(n["pr_count"]) + " merged PR(s)"
        for n in reports[2]["data"]["experts"]
    ] or ["No recent merged PR evidence."]
    expert_prs = [n for n in reports[2]["path"]["nodes"] if n["label"] == "PR"]
    body += ["- Evidence: " + cite(n["id"]) for n in expert_prs]
    body.append("## Similar incidents")
    body += [
        "- " + cite(n["id"]) + " — " + str(props[n["id"]].get("summary", ""))
        for n in reports[3]["data"]["incidents"]
    ] or ["No similar incidents recorded."]
    body.append("## Decision context")
    body += [
        "- " + cite(n["id"]) + " — " + str(props[n["id"]].get("context", ""))
        for n in reports[4]["data"]["decisions"]
    ] or ["No decision context recorded."]
    body += [
        "- Source: " + cite(n["id"]) for n in reports[4]["path"]["nodes"] if n["label"] == "PR"
    ]
    markdown = "\n\n".join(body)
    number, url = (None, "draft") if dry_run else _post_issue(*destination, title, markdown)
    suffix = uuid4().hex
    issue_id = "issue:draft-" + suffix if dry_run else "issue:" + str(number)
    incident_id = "incident:inc-" + suffix
    now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    params = {
        "service": service_id,
        "synthetic": True,
        "source_url": url,
        "incident": {
            "id": incident_id,
            "name": title,
            "source_url": "synthetic",
            "synthetic": True,
            "summary": summary,
            "started_at": now,
        },
        "issue": {
            "id": issue_id,
            # Distinct from the Incident node's full title (same incident, different
            # purpose) - both previously got `title` verbatim and rendered as two
            # identically-labeled graph nodes, looking like a duplicate.
            "name": "Drafted issue" if dry_run else "Filed issue",
            "source_url": url,
            "synthetic": True,
            "body": markdown,
            "state": "draft" if dry_run else "open",
        },
    }
    if number is not None:
        params["issue"]["number"] = number
    # Dry runs are UI-only: every "simulate alert" click used to leave a permanent
    # Incident/Issue node behind, even when nothing was actually filed. Only a real
    # filing (dry_run=False) is worth recording in the graph for future similar_incidents/
    # trace lookups - a draft is just this response's data, rendered by the frontend's
    # IssueCard, never written.
    combined = Evidence()
    combined.add(list(evidence.nodes.values()))
    if not dry_run:
        _, written = tools._run(q.ISSUE, params)
        combined.add(list(written.nodes.values()))
        combined.add(list(written.edges.values()))
    path = combined.render()
    edges = {
        (e["source"], e["target"], e["type"]): e
        for report in reports
        for e in report["path"]["edges"]
    }
    edges.update({(e["source"], e["target"], e["type"]): e for e in path["edges"]})
    path["edges"] = [edges[k] for k in sorted(edges)]
    return {
        "data": {
            "issue_id": issue_id,
            "dry_run": dry_run,
            "url": url,
            "incident_id": incident_id,
            "title": title,
            "body": markdown,
        },
        "cypher": q.ISSUE,
        "params": params,
        "path": path,
    }

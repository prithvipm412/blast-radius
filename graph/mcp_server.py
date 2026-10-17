"""Official MCP SDK stdio entry point: python -m graph.mcp_server."""

import asyncio
import inspect
import json
from functools import wraps

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from graph import tools

mcp = FastMCP("blast_radius_mcp")
TOOL_NAMES = (
    "search_entities",
    "blast_radius",
    "failure_path",
    "find_owners",
    "find_experts",
    "similar_incidents",
    "trace_decision",
    "critical_services",
    "single_points_of_failure",
    "team_clusters",
    "create_incident_issue",
)


def _mcp_callable(fn):
    @wraps(fn)
    async def invoke(**kwargs):
        result = await asyncio.to_thread(fn, **kwargs)
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(result))], structuredContent=result
        )

    invoke.__signature__ = inspect.signature(fn).replace(return_annotation=CallToolResult)
    return invoke


for name in TOOL_NAMES:
    writes = name in {"create_incident_issue", "critical_services"}
    mcp.add_tool(
        _mcp_callable(getattr(tools, name)),
        annotations=ToolAnnotations(
            readOnlyHint=not writes,
            destructiveHint=False,
            idempotentHint=not writes,
            openWorldHint=writes,
        ),
    )

if __name__ == "__main__":
    mcp.run(transport="stdio")

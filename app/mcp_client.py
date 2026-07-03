"""MCP client: how the agent discovers and calls tools served by mcp-server.

This module has no idea what the tools *do*, and no idea about RBAC -- it
only speaks the MCP protocol. Tool schemas are discovered from the MCP
server at runtime via `list_tools()` rather than hardcoded here, which is
what "clearly separates tool definitions from core agent logic" means in
practice: this file (and agent.py) would be unchanged if mcp_server/ added
a fifth tool tomorrow.

One deliberate exception: a small number of tool parameters exist on the
real MCP schema but must never be shown to (or filled in by) the model --
`create_next_action`'s `created_by`, which has to come from the caller's
verified identity, not from anything the LLM supplies. Those are filtered
out of what's shown to Gemini and re-injected here before the actual MCP
call, using the exact same non-forgeable-attribution approach as Step 4,
just re-implemented across the client/server boundary.
"""

import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://mcp-server:8001/mcp")

# tool name -> {parameter name the model must never see}
_HIDDEN_PARAMETERS: dict[str, set[str]] = {
    "create_next_action": {"created_by"},
}

# tool name -> {parameter name: field to read off the verified caller dict}
_INJECTED_PARAMETERS: dict[str, dict[str, str]] = {
    "create_next_action": {"created_by": "preferred_username"},
}


async def get_tool_declarations() -> list[dict]:
    """Discover the MCP server's tools and convert them into Gemini-style
    function tool declarations, with hidden/caller-injected parameters
    stripped out of what the model is shown.
    """
    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    declarations = []
    for t in result.tools:
        schema = dict(t.inputSchema)
        hidden = _HIDDEN_PARAMETERS.get(t.name, set())
        if hidden:
            schema = {
                **schema,
                "properties": {
                    k: v
                    for k, v in schema.get("properties", {}).items()
                    if k not in hidden
                },
                "required": [r for r in schema.get("required", []) if r not in hidden],
            }
        declarations.append(
            {
                "type": "function",
                "name": t.name,
                "description": t.description or "",
                "parameters": schema,
            }
        )
    return declarations


async def call_tool(tool_name: str, arguments: dict, caller: dict) -> dict:
    """Call a tool on the MCP server, injecting any caller-derived
    parameters (e.g. `created_by`) the model was never shown, and
    normalizing the MCP result back into a plain dict.
    """
    full_arguments = dict(arguments)
    for param, caller_field in _INJECTED_PARAMETERS.get(tool_name, {}).items():
        full_arguments[param] = caller.get(caller_field, "unknown")

    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, full_arguments)

    payload: object = {}
    if result.content and getattr(result.content[0], "text", None):
        try:
            payload = json.loads(result.content[0].text)
        except json.JSONDecodeError:
            payload = {"raw": result.content[0].text}

    if result.isError:
        message = payload.get("error", payload) if isinstance(payload, dict) else str(payload)
        return {"error": message}
    return payload

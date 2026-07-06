"""Acme MCP server -- exposes the five Acme-specific tools over MCP.

Runs over the `streamable-http` transport so it's reachable from the `app`
container over the docker network, at http://mcp-server:8001/mcp.
"""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

import tools

mcp = FastMCP(
    "acme-operations-tools",
    instructions=(
        "Tools for looking up Acme Operations customers and issues, and for "
        "recording recommended next actions on a specific issue."
    ),
    host="0.0.0.0",
    port=8001,
    stateless_http=True,
)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    """Liveness/readiness probe used by docker-compose's healthcheck --
    kept as a plain HTTP route alongside the MCP endpoint so the existing
    `curl -f http://localhost:8001/health` check keeps working unchanged.
    """
    return JSONResponse({"status": "ok"})


@mcp.tool(description="Retrieve a customer's profile (industry, account tier, primary contact) by customer name.")
def get_customer_profile(
    customer_name: Annotated[str, Field(description="The customer's name, e.g. 'Globex Corporation'")],
) -> dict:
    return tools.get_customer_profile(customer_name)


@mcp.tool(
    description=(
        "Retrieve all open or in-progress issues for a given customer, "
        "ordered by priority (most urgent first)."
    )
)
def get_open_issues_for_customer(
    customer_name: Annotated[str, Field(description="The customer's name")],
) -> dict:
    return tools.get_open_issues_for_customer(customer_name)


@mcp.tool(
    description=(
        "Retrieve a specific issue's details and its full chronological update "
        "history, for summarizing what has happened on that issue. Requires the "
        "numeric issue id -- call get_open_issues_for_customer first if you "
        "don't already know it."
    )
)
def summarize_issue_history(
    issue_id: Annotated[int, Field(description="The issue's numeric id")],
) -> dict:
    return tools.summarize_issue_history(issue_id)


@mcp.tool(
    description=(
        "Update a specific issue's status and append a note to its history "
        "explaining the change. Only available to support and admin roles "
        "-- sales users cannot call this (enforced by the caller, not by "
        "this tool)."
    )
)
def update_issue_status(
    issue_id: Annotated[int, Field(description="The issue's numeric id")],
    new_status: Annotated[
        str,
        Field(description="The issue's new status: one of 'open', 'in_progress', 'resolved', 'closed'"),
    ],
    note: Annotated[
        str,
        Field(description="A note describing what changed and why, recorded in the issue's history"),
    ],
    updated_by: Annotated[
        str,
        Field(
            description=(
                "The verified username of the caller making this update. "
                "Must be supplied by the calling agent from an authenticated "
                "identity, never left to the model to guess."
            )
        ),
    ],
) -> dict:
    return tools.update_issue_status(issue_id, new_status, note, updated_by)


@mcp.tool(
    description=(
        "Record a recommended next action for a specific issue. Only "
        "available to the admin role -- sales and support users cannot "
        "call this (enforced by the caller, not by this tool)."
    )
)
def create_next_action(
    issue_id: Annotated[int, Field(description="The issue's numeric id")],
    recommended_action: Annotated[str, Field(description="A concise, concrete recommended next step")],
    rationale: Annotated[str, Field(description="Why this action is recommended")],
    created_by: Annotated[
        str,
        Field(
            description=(
                "The verified username of the caller requesting this action. "
                "Must be supplied by the calling agent from an authenticated "
                "identity, never left to the model to guess."
            )
        ),
    ],
) -> dict:
    return tools.create_next_action(issue_id, recommended_action, rationale, created_by)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

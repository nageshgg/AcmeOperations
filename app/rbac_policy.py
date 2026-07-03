"""Which Keycloak roles may call which MCP tool.

This is deliberately the *only* thing this module knows. Tool definitions
and execution now live entirely in mcp_server/ (Step 5) -- this module
holds the authorization policy, which has to live here instead, because
enforcing it requires the caller's verified Keycloak identity, and that
identity only exists in this (`app`) container, where the bearer token was
validated. Neither side could enforce RBAC alone: the MCP server has no
idea who's calling it, and the agent loop has no idea what a tool does --
each container only knows the part of the picture it needs to.
"""

# create_next_action is the one write operation among the four required
# tools, and is withheld from sales_user (explicitly read-only per the brief).
TOOL_ROLE_POLICY: dict[str, set[str]] = {
    "get_customer_profile": {"sales_user", "support_user", "admin"},
    "get_open_issues_for_customer": {"sales_user", "support_user", "admin"},
    "summarize_issue_history": {"sales_user", "support_user", "admin"},
    "create_next_action": {"support_user", "admin"},
}


def check_access(tool_name: str, caller: dict) -> str | None:
    """Returns an error message if `caller` may not call `tool_name`, or
    `None` if the call is allowed. A tool with no policy entry is denied by
    default (fail closed) rather than silently allowed.
    """
    allowed_roles = TOOL_ROLE_POLICY.get(tool_name)
    if allowed_roles is None:
        return f"Unknown tool '{tool_name}' -- no access policy defined for it."
    if not (caller["_roles"] & allowed_roles):
        return (
            f"Access denied: your role(s) {sorted(caller['_roles'])} do not "
            f"include any of the roles required to call '{tool_name}': "
            f"{sorted(allowed_roles)}."
        )
    return None

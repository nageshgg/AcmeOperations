# sales_user: read-only -- can look up customers/issues/history but change
# nothing.
# support_user: read-only tools plus update_issue_status -- can update an
# issue's status/history in addition to everything sales_user can do.
# admin: full access, including create_next_action -- the only role that
# may record a recommended next action.
TOOL_ROLE_POLICY: dict[str, set[str]] = {
    "get_customer_profile": {"sales_user", "support_user", "admin"},
    "get_open_issues_for_customer": {"sales_user", "support_user", "admin"},
    "summarize_issue_history": {"sales_user", "support_user", "admin"},
    "update_issue_status": {"support_user", "admin"},
    "create_next_action": {"admin"},
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

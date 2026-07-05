"""The four Acme-specific tool implementations, exposed over MCP by server.py.

This module owns tool *logic* only (querying Postgres). It has no concept
of Keycloak roles or RBAC -- that's a deliberate boundary: authorization
decisions depend on the caller's verified identity, which only exists in
the `app` container (where the bearer token was validated), so RBAC is
enforced there, one layer above the MCP protocol boundary, before a tool
call ever reaches this container. This module trusts whatever it's asked
to run.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from db import execute, query


def _json_safe(value: Any) -> Any:
    """psycopg2 returns datetime/Decimal objects that aren't JSON-serializable
    by default; MCP tool results are serialized as JSON over the wire.
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _row_safe(row: dict) -> dict:
    return {k: _json_safe(v) for k, v in row.items()}


def _find_customer(customer_name: str) -> dict:
    """Resolve a customer name to a single row, tolerating case and partial
    matches. Returns `{"found": {...}}`, `{"not_found": True}`, or
    `{"multiple_matches": [...]}` so the agent can ask the user to
    disambiguate instead of guessing.
    """
    exact = query("SELECT * FROM customers WHERE name ILIKE %s", (customer_name,))
    if len(exact) == 1:
        return {"found": _row_safe(exact[0])}
    partial = query("SELECT * FROM customers WHERE name ILIKE %s", (f"%{customer_name}%",))
    if len(partial) == 1:
        return {"found": _row_safe(partial[0])}
    if len(partial) > 1:
        return {"multiple_matches": [c["name"] for c in partial]}
    return {"not_found": True}


def get_customer_profile(customer_name: str) -> dict:
    """Tool 1: retrieve a customer's profile by name."""
    result = _find_customer(customer_name)
    return result["found"] if "found" in result else result


def get_open_issues_for_customer(customer_name: str) -> dict:
    """Tool 2: retrieve all open/in-progress issues for a given customer,
    ordered by priority (critical first) then age.
    """
    lookup = _find_customer(customer_name)
    if "found" not in lookup:
        return lookup
    customer = lookup["found"]
    rows = query(
        """
        SELECT id, title, status, priority, created_at, updated_at
        FROM issues
        WHERE customer_id = %s AND status IN ('open', 'in_progress')
        ORDER BY
            CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                          WHEN 'medium' THEN 2 ELSE 3 END,
            created_at
        """,
        (customer["id"],),
    )
    return {
        "customer_name": customer["name"],
        "open_issue_count": len(rows),
        "issues": [_row_safe(r) for r in rows],
    }


def summarize_issue_history(issue_id: int) -> dict:
    """Tool 3: retrieve a specific issue's details plus its full
    chronological update history. This tool fetches ground-truth data only
    -- the actual prose summary is produced by the model reasoning over
    this structured result, not by this function.
    """
    issues = query(
        """
        SELECT i.*, c.name AS customer_name
        FROM issues i JOIN customers c ON c.id = i.customer_id
        WHERE i.id = %s
        """,
        (issue_id,),
    )
    if not issues:
        return {"error": f"No issue found with id {issue_id}"}
    updates = query(
        "SELECT author, update_text, created_at FROM issue_updates "
        "WHERE issue_id = %s ORDER BY created_at ASC",
        (issue_id,),
    )
    return {"issue": _row_safe(issues[0]), "updates": [_row_safe(u) for u in updates]}


VALID_ISSUE_STATUSES = {"open", "in_progress", "resolved", "closed"}


def update_issue_status(
    issue_id: int, new_status: str, note: str, updated_by: str
) -> dict:
    """Tool 4: update a specific issue's status and append a note to its
    history explaining the change.

    `updated_by` is expected to be the caller's *verified* username, passed
    in by the app-layer MCP client -- never a value the LLM itself supplied,
    same guarantee as `create_next_action`'s `created_by` below.
    """
    if not query("SELECT id FROM issues WHERE id = %s", (issue_id,)):
        return {"error": f"No issue found with id {issue_id}"}
    if new_status not in VALID_ISSUE_STATUSES:
        return {
            "error": (
                f"Invalid status '{new_status}'; must be one of "
                f"{sorted(VALID_ISSUE_STATUSES)}"
            )
        }
    issue_rows = execute(
        """
        UPDATE issues
        SET status = %s,
            updated_at = now(),
            closed_at = CASE WHEN %s IN ('resolved', 'closed') THEN now() ELSE closed_at END
        WHERE id = %s
        RETURNING id, customer_id, title, status, priority, created_at, updated_at, closed_at
        """,
        (new_status, new_status, issue_id),
    )
    update_rows = execute(
        """
        INSERT INTO issue_updates (issue_id, author, update_text)
        VALUES (%s, %s, %s)
        RETURNING id, issue_id, author, update_text, created_at
        """,
        (issue_id, updated_by, note),
    )
    return {"issue": _row_safe(issue_rows[0]), "update": _row_safe(update_rows[0])}


def create_next_action(
    issue_id: int, recommended_action: str, rationale: str, created_by: str
) -> dict:
    """Tool 5: record a recommended next action for a specific issue.

    `created_by` is expected to be the caller's *verified* username, passed
    in by the app-layer MCP client -- never a value the LLM itself supplied.
    See `app/mcp_client.py` for where that guarantee is actually enforced
    (this function has no way to check it itself).
    """
    if not query("SELECT id FROM issues WHERE id = %s", (issue_id,)):
        return {"error": f"No issue found with id {issue_id}"}
    rows = execute(
        """
        INSERT INTO next_actions (issue_id, recommended_action, rationale, created_by)
        VALUES (%s, %s, %s, %s)
        RETURNING id, issue_id, recommended_action, rationale, status, created_by, created_at
        """,
        (issue_id, recommended_action, rationale, created_by),
    )
    return _row_safe(rows[0])

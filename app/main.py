"""Acme Operations API — FastAPI entrypoint.

`/health` is unauthenticated (it's just the container healthcheck). The
`/me` and `/admin/ping` routes exist only to prove the Keycloak
bearer-token validation + RBAC flow works end-to-end at this checkpoint;
the real tool endpoints (Step 4) and MCP wiring (Step 5) sit behind the
same `auth.require_role(...)` dependency.
"""

from fastapi import Depends, FastAPI

from auth import require_role

app = FastAPI(title="Acme Operations API")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness/readiness probe used by docker-compose's healthcheck."""
    return {"status": "ok"}


@app.get("/me")
def me(user: dict = Depends(require_role("sales_user", "support_user", "admin"))) -> dict:
    """Returns the caller's identity as decoded from their bearer token.
    Any of the three roles can call this — it's just proof that
    authentication works, not a role-specific capability.
    """
    return {"username": user.get("preferred_username"), "roles": sorted(user["_roles"])}


@app.get("/admin/ping")
def admin_ping(user: dict = Depends(require_role("admin"))) -> dict:
    """Admin-only route: proves RBAC actually rejects non-admin roles,
    not just that authentication succeeded.
    """
    return {"message": f"pong, admin {user.get('preferred_username')}"}

"""Acme Operations API — FastAPI entrypoint.

`/health` is unauthenticated (it's just the container healthcheck). `/me`
and `/admin/ping` exist only to prove the Keycloak bearer-token + RBAC flow
works end-to-end. `/chat` is the open-ended agentic entrypoint: it hands
the caller's message and verified identity to the agent loop, which
decides which tool(s) to call (RBAC-enforced per tool call, not just per
route), and continues a prior conversation via Redis-backed session memory
(Step 7) when the caller supplies a `conversation_id`.
`/skills/escalation-summary` is different in kind, not just in name: it's
a fixed, structured workflow (Step 6) rather than an open-ended
conversation.

The HTTP middleware below is Step 8's observability requirement: every
request gets a request ID (propagated via `observability`'s contextvar so
every log line emitted anywhere during that request -- including tool
calls logged in agent.py -- carries the same id), plus a structured
start/end/error log with latency.
"""

import logging
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import observability
import session_store
from agent import run_agent
from auth import require_role
from skills.escalation_summary import generate_escalation_summary

observability.configure_logging()

app = FastAPI(title="Acme Operations API")

# Read once at import time -- this is a small, static file, so there's no
# need to hit disk on every request to "/".
_INDEX_HTML = (Path(__file__).parent / "static" / "index.html").read_text()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Serves the single-page frontend (login, chat, agent activity panel).

    This is a plain `GET /` route rather than a `StaticFiles` mount, so it
    can't shadow any existing API route (`/chat`, `/me`, etc.) -- it only
    ever matches the exact root path.
    """
    return _INDEX_HTML


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Assigns a request id (or honors an incoming `X-Request-ID`, so a
    caller's own tracing can line up with ours), logs a start/end/error
    event with latency, and echoes the id back in the response header so a
    client can correlate their request with these logs.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    observability.set_request_id(request_id)
    start = time.monotonic()
    observability.log_event("request_start", method=request.method, path=request.url.path)

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        observability.log_event(
            "request_error",
            level=logging.ERROR,
            method=request.method,
            path=request.url.path,
            duration_ms=duration_ms,
            error=str(exc),
        )
        raise

    duration_ms = round((time.monotonic() - start) * 1000, 1)
    observability.log_event(
        "request_end",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


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


class ChatRequest(BaseModel):
    message: str
    # Omit on the first message of a conversation; the response returns a
    # generated one. Supply it on follow-ups to keep context (Step 7).
    conversation_id: str | None = None


@app.post("/chat")
async def chat(
    req: ChatRequest,
    user: dict = Depends(require_role("sales_user", "support_user", "admin")),
) -> dict:
    """Agentic chat endpoint. Open to all three roles -- RBAC is enforced
    per tool call inside the agent loop, not at this route level, since a
    sales_user is allowed to ask questions (and get read-tool answers) but
    not to trigger the one write-capable tool.

    Conversation continuity: `req.conversation_id` (client-supplied, or
    generated here on a caller's first message) is a Redis key holding the
    Gemini interaction id from that conversation's last turn -- not the
    message history itself, which the Interactions API already retains
    server-side once you pass `previous_interaction_id`. See
    session_store.py for why Redis (not Postgres) is the right store for
    this.
    """
    conversation_id = req.conversation_id or str(uuid.uuid4())
    previous_interaction_id = await session_store.get_previous_interaction_id(conversation_id)

    result = await run_agent(req.message, user, previous_interaction_id=previous_interaction_id)

    if "interaction_id" in result:
        await session_store.set_previous_interaction_id(conversation_id, result["interaction_id"])

    result["conversation_id"] = conversation_id
    return result


class EscalationSummaryRequest(BaseModel):
    customer_name: str


@app.post("/skills/escalation-summary")
async def escalation_summary(
    req: EscalationSummaryRequest,
    user: dict = Depends(require_role("sales_user", "support_user", "admin")),
) -> dict:
    """Customer Escalation Summary Skill. Open to all three roles -- it
    only reads data (profile + open issues + history), the same as the
    read-side of /chat, so there's no write capability to restrict here.
    """
    return await generate_escalation_summary(req.customer_name, user)

"""Acme Operations API — FastAPI entrypoint.

This is a Step 1 placeholder: it exists only to prove the `app` container
builds, starts, and reports healthy inside docker-compose. Real routes (agent
chat endpoint, tool endpoints, auth-protected routes) are added in later
steps.
"""

from fastapi import FastAPI

app = FastAPI(title="Acme Operations API")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness/readiness probe used by docker-compose's healthcheck."""
    return {"status": "ok"}

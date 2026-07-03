"""Acme MCP server — placeholder entrypoint.

This is a Step 1 placeholder: it exists only to prove the `mcp-server`
container builds, starts as its own service, and reports healthy inside
docker-compose. The real implementation (a FastMCP server exposing the four
Acme-specific tools) is built in Step 5, once the tools themselves exist
(Step 4) and the database/schema they read from exists (Step 2).
"""

from fastapi import FastAPI

app = FastAPI(title="Acme MCP Server (placeholder)")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness/readiness probe used by docker-compose's healthcheck."""
    return {"status": "ok"}

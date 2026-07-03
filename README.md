# Acme Operations — Agentic Enterprise Assistant

Take-home technical assessment prototype: an agentic assistant that lets Acme
Operations staff (sales, support, ops) ask natural-language questions about
customers and issues, with tool-calling, MCP, RBAC via Keycloak, and an
auditable, observable request path.

> **Status:** Build in progress. This README is being filled in incrementally
> as each step lands (see project log below). Full setup instructions,
> architecture diagram, trade-offs, and eval results land at the final step.

## Tech stack

- **API**: FastAPI (Python 3.11+)
- **LLM**: Google Gemini (`gemini-2.0-flash` by default) — see
  [Trade-offs](#trade-offs) for why this deviates from a Claude/Anthropic-based
  agent loop
- **MCP server**: Python MCP SDK (FastMCP), its own container
- **Datastore**: PostgreSQL 16
- **Session/conversation memory**: Redis 7
- **AuthN/AuthZ**: Keycloak (realm auto-imported via `--import-realm`), RBAC
  with `sales_user` / `support_user` / `admin` roles
- **Orchestration**: Docker Compose (single `docker compose up` brings up all
  5 services)

## Setup

_(Full instructions land in Step 9. For now: `cp .env.example .env`, fill in
`GEMINI_API_KEY`, then `docker compose up --build`.)_

## Architecture

_(Mermaid diagram lands in Step 9.)_

## MCP: why it's used here

_(Written up in Step 5, alongside the MCP server implementation.)_

## Trade-offs

- **LLM provider: Gemini instead of Anthropic Claude.** The original brief
  specified the Anthropic API. We switched to Google Gemini because it has a
  usable free tier, which matters for a take-home assessment that shouldn't
  require ongoing API spend to demo or re-run. The agent-loop and tool-calling
  design (dynamic tool selection, MCP integration, structured skill output) is
  provider-agnostic in intent; the Gemini function-calling API is used in
  place of Anthropic's Messages API tool-use.

## Evaluation

_(Eval set + runner + results land in Step 8.)_

## AI tool usage

See [AI_USAGE_NOTES.md](./AI_USAGE_NOTES.md) for what was delegated to AI
tooling per checkpoint, how it was reviewed, and what should not be trusted
to AI without human oversight.

See [TROUBLESHOOTING_LOG.md](./TROUBLESHOOTING_LOG.md) for a command-level
engineering log of every issue hit while building this (symptom, root cause,
exact commands run, and why), one section per checkpoint.

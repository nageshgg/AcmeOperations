# AI Usage Notes

This file logs, per checkpoint: what was delegated to Claude Code, how it was
reviewed/validated, any errors or hallucinations found and corrected, and
observations on what should NOT be trusted to AI tools without human oversight
in a real client engagement. Updated after every step.

---

## Step 0 / Step 1 — Repo skeleton + docker-compose.yml

**What was delegated:**
Claude Code was asked to scaffold the project: create the `AcmeOperations/`
directory, initialize git, write `.gitignore`, `.env.example`, README/
AI-usage-notes skeletons, and a `docker-compose.yml` bringing up 5 services
(Postgres, Redis, Keycloak, a placeholder MCP server container, and a
placeholder FastAPI app container) with healthchecks.

**Decisions made during this step (recorded for traceability):**
- LLM provider changed from the originally-specified Anthropic API to Google
  Gemini, at the user's explicit request, for cost reasons (Gemini has a free
  tier). This is a deviation from the original written brief's tech stack —
  flagged in the README trade-offs section. Everywhere the brief's tools/MCP/
  Skill/RBAC requirements reference "the agent," those requirements are
  unchanged; only the model provider and its tool-calling wire format differ.
- Keycloak image pinned to `quay.io/keycloak/keycloak:26.0` for reproducibility
  in this step. This should be re-verified against current Keycloak docs when
  we configure the realm export / hostname settings in Step 3, since that step
  explicitly requires checking current documentation rather than relying on
  memory.
- `app` and `mcp_server` are stub FastAPI services in this step (just a
  `/health` endpoint) — real tool-calling and MCP logic land in Steps 4–5.
  This keeps Step 1 scoped to "does the whole stack boot and report healthy,"
  per the user's instruction to build in small, reviewable, confirmable steps.

**Errors found and corrected during this step:**
Two issues surfaced only by actually running the stack, not by reading the
compose file — full command-by-command detail (symptom, root cause, exact
commands, why that approach) is in
[TROUBLESHOOTING_LOG.md](./TROUBLESHOOTING_LOG.md#step-1--keycloak-container-reported-unhealthy-despite-keycloak-itself-running-fine):
1. A Keycloak healthcheck that looked correct by inspection hung indefinitely
   due to an HTTP keep-alive connection never reaching EOF — Keycloak itself
   was healthy the whole time, but the container was reported `unhealthy` and
   blocked the dependent `app` container from starting.
2. Two Keycloak env vars (`KEYCLOAK_ADMIN`/`KEYCLOAK_ADMIN_PASSWORD`) were
   using a deprecated name, caught from the container's own startup warning
   logs rather than guessed.

The general lesson (relevant to the "what shouldn't be trusted to AI without
oversight" question below): a docker-compose file that *looks* right can
still hide a healthcheck bug that only manifests at runtime. "I wrote a
plausible healthcheck" is not the same claim as "I watched it pass" — the
gap between those two is exactly where this bug lived.

**How this was validated:**
Ran `docker compose up -d --build`, confirmed via `docker compose ps` that
all 5 containers reach `healthy`, and curled `/health` on both `app` and
`mcp-server` plus the Keycloak admin console root, confirming HTTP 200 on
all three.

**How the user can re-verify:**
`docker compose up --build` and confirm all 5 containers reach a healthy
state (see the verification instructions given alongside this checkpoint in
conversation).

**What should NOT be trusted to AI tools without human oversight:**
- Model/version pins for infrastructure (Keycloak, Postgres, Redis base
  images) should be spot-checked by a human against current release notes
  before a real engagement ships — an AI assistant's training data can lag
  the actual current stable release, and guessing wrong here silently breaks
  reproducibility for whoever clones the repo later.
- The decision to switch LLM providers mid-brief is a business/scope decision,
  not a technical one — it was correctly escalated to the user rather than
  assumed, but in a real client engagement this kind of deviation from a
  written spec should always be confirmed in writing with the client, not just
  in a chat turn.

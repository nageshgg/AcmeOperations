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

---

## Step 2 — PostgreSQL schema + seed data

**What was delegated:**
Claude Code was asked to design and write the full schema (`customers`,
`issues`, `issue_updates`, `next_actions`, `users`) and a realistic seed
dataset sized to exercise every agent capability in the brief, as two
`db/init/*.sql` files that auto-run via the official Postgres image.

**How this was validated:**
Not just read — actually run. Rebuilt the stack with a fresh (empty)
Postgres volume so the init scripts would execute, then verified with
`psql`: table list matches the schema, row counts match the seed plan
exactly (5 customers; 16 issues, 10 open/6 closed; 41 issue_updates; 2 seeded
next_actions; 3 users with the expected roles), and two representative join
queries (open issues for a named customer; full chronological update history
for a specific issue) returned correct, correctly-ordered results. See
[TROUBLESHOOTING_LOG.md](./TROUBLESHOOTING_LOG.md#step-2--no-issues-one-gotcha-worth-recording-for-future-re-testing)
for the exact commands.

**Observations relevant to AI oversight on this step:**
- The seed data content (customer names, issue narratives, escalation
  scenarios) is synthetic and plausible-sounding by construction — that's
  the point of an LLM writing fictional demo data, but it's worth being
  explicit that none of it was validated against anything real because there
  was nothing real to validate it against. In a real client engagement,
  seed/test data of this kind should be clearly and permanently labeled as
  synthetic wherever it could be mistaken for production data, especially if
  it ever migrates into a shared or long-lived environment.
- Row-count and join verification (the "how this was validated" section
  above) is exactly the kind of check that's cheap to run and easy to skip —
  an AI assistant asserting "seed data loaded successfully" without actually
  querying the database back is a claim, not a verification. This is worth
  watching for in any AI-assisted database work: schema/seed files that
  parse and apply without error are not the same claim as data that is
  structurally correct.

---

## Step 3 — Keycloak realm + FastAPI bearer-token validation + RBAC

**What was delegated:**
Claude Code was asked to author a Keycloak realm as a hand-written partial
realm-representation JSON (not clicked through the admin console and
exported — see below for why that distinction matters), wire it into
`docker-compose.yml` via `--import-realm`, fix the browser-vs-internal-network
issuer mismatch the brief explicitly calls out, and write the FastAPI
JWT-validation + RBAC dependency layer (`app/auth.py`) plus two demo routes
proving the flow end-to-end.

**How this was validated:**
Every claim in this step was checked by actually running it, not by
inspecting the config/code and reasoning that it should work:
- Confirmed the issuer-mismatch fix (`KC_HOSTNAME`) by diffing the OIDC
  discovery document's `issuer` field fetched from the host vs. from inside
  the `app` container — they must be byte-identical for token validation to
  work regardless of how a token was obtained.
- Fetched a real access token for all three seeded users (`sales_user`,
  `support_user`, `admin`) via Keycloak's password grant, then called both
  `/me` (should succeed for all three) and `/admin/ping` (should succeed
  only for `admin`) with each token — 6 requests, all returned the expected
  status code.
- Checked the negative cases too, not just the happy path: no token, and a
  garbage token, both correctly rejected (401).
See
[TROUBLESHOOTING_LOG.md](./TROUBLESHOOTING_LOG.md#step-3--app-container-crash-looped-keyerror-keycloak_issuer)
for the exact commands and two issues found along the way (a stale local
`.env` missing new variables, and FastAPI's `HTTPBearer` defaulting to `403`
instead of `401` for missing credentials — both fixed and re-verified).

**Decisions made during this step (recorded for traceability):**
- The realm was authored directly as JSON rather than built by hand in the
  Keycloak admin console and then exported. This was a deliberate choice for
  reproducibility (`git clone` + `docker compose up` must fully recreate the
  realm with no manual admin-console steps) — but it means the realm's
  correctness rests on my knowledge of Keycloak's realm-representation JSON
  schema being accurate, which is exactly the kind of claim that needed
  runtime verification (see above) rather than being trusted on inspection
  alone.
- Test user passwords are stored in plaintext in `keycloak/realm-export.json`
  (which is committed to git). This is acceptable *only* because these are
  disposable local-dev credentials for a take-home assessment with no real
  data behind them — this pattern must never be replicated for anything
  resembling a real environment. Flagged explicitly here and in
  `.env.example` so it isn't mistaken for an acceptable practice generally.

**What should NOT be trusted to AI tools without human oversight:**
- Auth/authz code is exactly the category where "looks right" and "is right"
  diverge most dangerously, and where the cost of being wrong is highest (a
  subtly-broken RBAC check fails silently — it doesn't crash, it just lets
  the wrong people through, or locks the right people out, and nobody
  notices until an audit or an incident). Every claim about this step's auth
  flow was independently re-verified against a running system precisely
  because "the code looks correct" is not a sufficient bar for this category
  of change, AI-written or not. In a real engagement, auth/authz logic
  written or modified by an AI tool should get a dedicated human security
  review pass before shipping, separate from ordinary code review.
- The decision to store realistic-looking (if fake) passwords in a
  committed file is a judgment call that trades reproducibility for a
  secret-hygiene compromise. An AI assistant will make that trade
  automatically when asked for full reproducibility; a human reviewer should
  be the one deciding whether that trade is acceptable for a given
  repository's actual visibility and lifespan, not the assistant.

**Addendum — the Keycloak Account Console 401 the user found by actually
testing the browser flow themselves:**
This is worth calling out on its own because it's the clearest example so
far in this project of why the user's insistence on a manual verification
step (rather than accepting "I tested it and it works") mattered. Every
scripted check I had run before that point — token issuance for all three
roles, `/me`, `/admin/ping`, negative cases — passed. None of them would
have caught this bug, because it lived entirely inside Keycloak's own
bundled Account Console UI and its interaction with a subtlety of
`--import-realm` (imported users don't automatically get the realm's
default role bundle the way admin-console-created users do). The actual
root cause (a missing `default-roles-acme-operations` role assignment,
which meant tokens carried no `aud` claim, which Keycloak's own Account REST
API then rejected) took real investigative work to isolate — several
plausible-sounding hypotheses (a leaked protocol mapper, a
`localhost`-vs-`127.0.0.1` mismatch, a `Secure`-cookie-over-HTTP issue) were
tested and ruled out one at a time against the running system, rather than
picking the first plausible story and calling it fixed. See
[TROUBLESHOOTING_LOG.md](./TROUBLESHOOTING_LOG.md#step-3--keycloaks-own-account-console-showed-something-went-wrong-http-401)
for the full investigation.

The general lesson: a bearer-token flow can be thoroughly, correctly
verified and a *browser*-based login flow can still be broken, because they
exercise different code paths (the account console depends on Keycloak's
own default-role/audience machinery that our own FastAPI validation never
touches). "I verified the API" and "I verified the product" are different
claims — this is exactly the gap a human clicking through the actual UI is
positioned to catch that an API-level test suite is not.

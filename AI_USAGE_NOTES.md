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

---

## Step 4 — Four tools + Gemini agent loop with RBAC at the tool layer

**What was delegated:**
Claude Code was asked to implement the four required tools
(`get_customer_profile`, `get_open_issues_for_customer`,
`summarize_issue_history`, `create_next_action`) against the Step 2 schema,
and a real agentic tool-calling loop using Google's Gemini API (switched
from Anthropic earlier in this project, per your explicit direction) —
with RBAC enforced per tool call based on the caller's verified Keycloak
role, not by trusting the model's own behavior.

**A deliberate research step before writing any agent code:**
Gemini's Python SDK has moved to a new "Interactions API" that I was not
confident about from training data alone (my last confirmed knowledge was
of the older `generate_content`-based function calling). Two web
documentation lookups gave inconsistent detail on how to submit a function
result back to the model. Rather than pick one and hope, I installed the
actual SDK in an isolated scratch environment, read its generated model
classes directly to get the real field names, and confirmed the full
round-trip against the live Gemini API with a throwaway test script before
writing any of `app/agent.py`. Full detail in
[TROUBLESHOOTING_LOG.md](./TROUBLESHOOTING_LOG.md#step-4--verifying-the-gemini-interactions-api-shape-before-trusting-it).
This is a direct example of "verify before trusting a stale or uncertain
API surface" — the same principle used for the Keycloak version pin in
Step 1, applied here because the LLM provider is the part of this project
furthest from a stable, well-documented-in-training-data API given how
recently it changed.

**How this was validated — the RBAC-at-the-tool-layer requirement
specifically:**
This is the part of the brief most likely to be probed by an assessor, so
it got the most scrutiny. Ran real conversations through `/chat` for all
three roles and inspected both the final reply *and* the structured
`tool_calls` trace (not just the reply text, which could look plausible
while the underlying tool call silently failed or was skipped):
- `sales_user` asking to both summarize an issue *and* create a next
  action: the summarization tool call succeeded, the create-next-action
  tool call was rejected with an explicit RBAC error
  (`"Access denied: your role(s) [...sales_user...] do not include any of
  the roles required..."`), and the model's final reply correctly told the
  user it couldn't record the action rather than pretending it had.
- `support_user` making the identical request: both tool calls succeeded,
  and the resulting row was confirmed via a direct `psql` query against
  `next_actions` — with `created_by` correctly set to `support_user` (taken
  from the verified JWT identity, never from anything the model itself
  supplied as an argument, so the model has no path to forge attribution).
- `admin` asking for a customer profile: confirmed the returned data
  (account tier, contact) matches the Step 2 seed data exactly.

**Decisions made during this step (recorded for traceability):**
- `summarize_issue_history` deliberately does *not* generate the summary
  itself — it returns the issue plus its full raw update history as
  structured data, and the model produces the actual prose synthesis. This
  keeps the tool as a pure data-retrieval boundary (auditable, testable,
  swappable) and the reasoning/synthesis where it belongs, with the LLM.
- `create_next_action` is the only tool withheld from `sales_user` among
  the four required tools, since it's the only one that writes — matching
  the brief's "sales_user: read-only" / "support_user: read and update"
  language using the minimum tool surface specified, rather than inventing
  a fifth tool to more finely distinguish `support_user` from `admin`.

**What should NOT be trusted to AI tools without human oversight:**
- The RBAC test above is only as good as the scenarios actually tried. I
  tested "role X attempts the one write-capable tool" and "role X attempts
  a read tool," but did not exhaustively test every tool against every
  role, nor adversarial phrasings designed to trick the model into
  attempting the restricted action indirectly (e.g., asking it to "update
  the database directly" or role-play framings). The server-side RBAC
  check does not depend on the model behaving well or being tricked — it
  rejects unauthorized tool calls unconditionally regardless of how the
  model was persuaded to attempt one — but a human reviewer should still
  probe adversarial phrasing before treating RBAC as fully proven, rather
  than accepting a handful of straightforward test cases as sufficient
  coverage for an access-control claim.
- Tool descriptions and the system instruction were written to *guide* the
  model's behavior (e.g., "don't guess or fabricate data," "tell the user
  which role is required"), but nothing stops a sufficiently unusual
  request from getting a plausible-sounding wrong answer that isn't
  grounded in an actual tool call. The eval suite in Step 8 needs to
  specifically check "responses grounded in database results" as its own
  criterion, separate from "did the right tool get called" — those are
  different failure modes and both matter.

---

## Step 5 — Custom MCP server (own container) + agent consumes tools via MCP

**What was delegated:**
Claude Code was asked to move the four tools from Step 4's in-process
Python calls to a real Model Context Protocol server running as its own
container, with the FastAPI app becoming an MCP *client* that discovers
tool schemas at runtime (not hardcoded) and dispatches calls over the
network via the MCP protocol.

**Another deliberate research step, same discipline as Step 4:**
The Python MCP SDK is a second external, evolving API surface this project
depends on. Rather than write `mcp_server/server.py` from memory, the
actual `mcp` package was installed in a scratch venv and its `FastMCP`
class inspected directly (constructor signature, `run()`'s transport
options, a live two-file test of the full list-tools/call-tool round trip)
before any real code was written. Detail in
[TROUBLESHOOTING_LOG.md](./TROUBLESHOOTING_LOG.md#step-5--same-verify-before-building-approach-for-the-mcp-sdk).

**A real bug found by testing, not by review:**
A Gemini free-tier rate limit (exhausted by this session's own heavy
testing volume across Steps 4 and 5) crashed a `/chat` request with an
opaque 500 -- but only *after* the underlying tool call (a database write)
had already succeeded. The bug wasn't the rate limit itself; it was that
`run_agent` had no error handling around the Gemini API calls, so a
provider-side failure on the *second* call in a tool-calling round trip
destroyed the response entirely, hiding that real work had already been
done. This is exactly the kind of failure mode that a quick manual test
("does /chat work") would miss, because it only surfaces under sustained
load or exhausted quota, not on a single clean call. Fixed by catching the
SDK's public `APIError` and returning a normal, well-formed response that
surfaces what tool calls succeeded and a plain explanation of what failed,
rather than an opaque crash. Also switched the default model from
`gemini-3.5-flash` to `gemini-2.5-flash`, since the newer model's free-tier
quota proved too fragile for a project that still has to survive an eval
suite and a grader's own manual testing. Full root-cause detail in
[TROUBLESHOOTING_LOG.md](./TROUBLESHOOTING_LOG.md#step-5--gemini-free-tier-rate-limit-crashed-a-request-mid-flight-real-bug-not-research).

**How the MCP separation was validated (not just asserted):**
- Confirmed the MCP server's *raw* advertised schema for `create_next_action`
  includes `created_by` as a required parameter (it has to -- the tool
  genuinely needs it), then separately confirmed `app/mcp_client.py`'s
  `get_tool_declarations()` strips it out before anything is shown to
  Gemini -- these are two different claims ("the tool needs this param" vs
  "the model is never shown this param") and both were checked
  independently rather than assuming the filtering code worked because it
  compiled.
- Re-ran the full Step 4 RBAC test matrix (sales_user read success, write
  denial, support_user write success with DB-verified `created_by`)
  against the new client/server architecture to confirm the refactor
  didn't quietly change the security properties already proven in Step 4.
  A multi-tool-chaining request ("profile + open issues + summarize the
  most urgent one" in one message) also confirmed the agent still reasons
  across multiple tool calls correctly when tool schemas come from a
  remote MCP server instead of a local Python dict.

**What should NOT be trusted to AI tools without human oversight:**
- The rate-limit crash is a good illustration of a broader pattern worth
  calling out explicitly: an AI assistant tends to test the *happy path*
  thoroughly (and did, extensively, in Step 4) but won't necessarily think
  to ask "what does sustained/repeated use of this integration look like,
  and what happens when a third-party dependency fails partway through a
  multi-step operation?" until it actually happens. A human reviewer
  building anything with a paid or rate-limited external API dependency
  should deliberately ask that question rather than waiting to discover it
  the way this session did.
- Switching the default model to work around a quota limit is a reasonable
  engineering call for a take-home assessment, but in a real client
  engagement, a model substitution driven by cost/quota constraints -- even
  a same-family, same-vendor substitution -- changes response quality and
  behavior in ways that should be evaluated against the actual product
  requirements, not decided unilaterally by an AI assistant chasing the
  error away. Here it was safe because both models were already being
  treated as interchangeable via an env var; that would not always be true.

---

## Step 6 — Customer Escalation Summary Skill

**What was delegated:**
Claude Code was asked to implement the brief's required Skill as a fixed,
structured, repeatable workflow (not a one-off prompt): given a customer
name, gather profile + open issues + full update history via the existing
MCP tools, and return exactly four fields (executive summary, risk level,
recommended next action, missing information) from a single Gemini call.

**A real, load-bearing finding, not just a research note:**
Gemini's Interactions API has a documented `response_format.schema`
parameter described as constraining output to a JSON schema. It is not.
Testing found the API accepts it silently and produces valid JSON that
simply ignores the requested key structure entirely. This was caught
*before* it became a hidden bug in the shipped Skill, by deliberately
testing the schema-enforcement claim in isolation (a trivial schema
worked; the real schema with an enum field did not) rather than trusting
the first working-looking test result. See
[TROUBLESHOOTING_LOG.md](./TROUBLESHOOTING_LOG.md#step-6--geminis-response_formatschema-parameter-is-accepted-but-not-enforced)
for the full isolation sequence. The fix — describing the schema in the
system instruction and independently validating the parsed result in
code, with one corrective retry — is the actual guarantee this skill's
"structured output" promise rests on, not the API parameter that looks
like it should be doing that job.

**How this was validated:**
Ran the real skill end-to-end against an account with genuine escalation
material (Wayne Enterprises — a critical production outage plus a stalled
medium-priority issue) and confirmed: exactly the four required keys were
present, `risk_level` was a valid enum value, and — checked specifically,
not just "it looks plausible" — the content directly referenced facts only
present in the actual seed data (the "second outage this quarter" phrasing
from the real issue update, the real account contact's name). Also
verified two failure paths return a clean `error` field *before* any
Gemini call is made (nonexistent customer name; an ambiguous partial match
across two real customers) — cheap, deterministic checks that don't burn
API quota on inputs that can't succeed.

**What should NOT be trusted to AI tools without human oversight:**
- This is the second time in this project (after the Keycloak
  `default-roles` bug in Step 3) that a component *looked* correct because
  it produced a plausible, valid-shaped result, while a specific
  documented guarantee underneath it silently didn't hold. An AI assistant
  building a "structured output" feature will readily reach for the
  API's own structured-output parameter because that's the obviously
  "correct" design — the discipline that catches it when the parameter is
  actually broken is running an isolation test against the *specific*
  claim being relied on ("does this constrain to *this* schema," not "does
  this produce JSON at all"), not a general smoke test. A human reviewer
  evaluating AI-written code that claims structured/guaranteed output
  should ask what, specifically, was tested to justify that guarantee.

---

## Step 7 — Redis session memory (with TTL) for follow-up context

**What was delegated:**
Claude Code was asked to add conversation continuity to `/chat`: a
`conversation_id` backed by Redis, storing the Gemini `interaction.id`
from a conversation's last turn (not the message history itself, which
Gemini's Interactions API already retains server-side once
`previous_interaction_id` is passed), with a 30-minute TTL.

**How this was validated — and a note on catching a false alarm:**
A two-turn test was the real proof: turn one asked about Stark Industries'
open issues (which returned two, in a specific order); turn two, using the
`conversation_id` from turn one's response, asked to *"summarize the
history of the first one you just mentioned"* — with no customer name or
issue id repeated. The agent correctly resolved this to the right issue,
which is only possible if the prior turn's context was genuinely retained
server-side across two separate HTTP requests, not a coincidence or a
lucky guess. The Redis key's TTL was also checked directly via
`redis-cli TTL` to confirm the 30-minute expiry is actually configured, not
just that a key exists.

Midway through this, a test script threw what looked like a JSON parsing
bug in the API's response. It wasn't — it was this session's own bash
one-liner (piping curl output through command substitution into a Python
`sys.stdin` read) mangling the bytes in transit; writing the response to a
file and loading it directly showed clean, valid JSON. This is recorded in
[TROUBLESHOOTING_LOG.md](./TROUBLESHOOTING_LOG.md#step-7--no-app-bugs-one-shell-scripting-false-alarm-worth-recording)
specifically because verifying which side of a test actually has the bug
— the code, or the test harness — is exactly the discipline this project's
debugging log is meant to demonstrate, not just the cases where the app
was at fault.

**What should NOT be trusted to AI tools without human oversight:**
- An AI assistant investigating its own test failure has an incentive
  structure worth naming: it's faster to "fix" a failure by changing the
  code under test than to first rule out the test harness itself, and a
  plausible-looking error message (here, a real Python traceback) can look
  like sufficient evidence on its own. The correct habit — inspect the
  actual bytes/state independently before changing either side — is one a
  human reviewer should watch for being skipped, especially under time
  pressure, since skipping it risks "fixing" correct code in response to a
  broken test.

---

## Step 8 — Eval set + eval runner + observability logging

**What was delegated:**
Claude Code was asked to build: (1) structured JSON logging with a
request ID threaded through every log line (tool calls, request/response
traces, errors, latency), and (2) an 8-case eval suite covering the four
required dimensions (tool selection, grounding, RBAC, next-action
reasonableness), runnable via a single script against the live stack.

**A bug that had been silently broken since Step 5, only surfaced by
running the eval suite:**
The exception handling added in Step 5 to gracefully degrade on Gemini API
failures was catching the wrong exception class the entire time —
confirmed via `issubclass(actual_raised_exception, caught_class) ->
False`. It had looked correct, compiled, and even seemed to "work" in
Step 5's own narrow testing window, but structurally could never have
caught the real failure mode. This is a notable example of something
worth calling out explicitly: **a fix that was never actually exercised
under the real failure condition it was written for gave false confidence
for three full steps (5, 6, 7) before the eval suite's heavier request
volume finally triggered the exact scenario it was supposed to handle.**
See
[TROUBLESHOOTING_LOG.md](./TROUBLESHOOTING_LOG.md#step-8--the-step-5-rate-limit-fix-never-actually-worked-wrong-exception-class).

**A real infrastructure constraint surfaced and escalated, not silently
routed around:**
Google's Gemini free tier caps at 20 requests/day *per model* — confirmed
from the actual quota violation metadata, not guessed from the error
message. This was exhausted purely by this session's own testing volume
and would have blocked the eval suite (and any future grading) from
completing. Rather than silently shrinking the eval suite to fit under
that limit (which would have quietly reduced eval coverage to work around
an infrastructure choice), this was surfaced to the user as an explicit
decision (`AskUserQuestion`) with three real options and their trade-offs.
The user chose to enable billing, which was verified to actually work
before continuing, rather than assumed.

**Eval scoring methodology — and a real lesson in what "grounding" checks
should verify:**
The eval runner mechanically scores tool selection, RBAC, and grounding
via a live API check (not a human reading transcripts, and not a second
LLM-as-judge call, which would double the API cost this same step just
worked around). "Next-action reasonableness" is explicitly *not*
mechanically scored — the eval report captures the actual recommendation
text for human judgment instead of pretending a keyword match can settle
a subjective call it can't. During development, one case's grounding check
broke three times in three consecutive runs, each time because the model
used a different (equally correct) English phrasing for "this customer
doesn't exist." The fix wasn't a better keyword list — it was recognizing
that checking the model's *prose* for a fact is inherently fragile when
the fact has many valid phrasings, and switching to checking the
*underlying tool's own structured result* instead, which has no
phrasing-variance problem at all. Full detail in
[TROUBLESHOOTING_LOG.md](./TROUBLESHOOTING_LOG.md#step-8--eval-scoring-keyword-matching-free-text-is-fragile-check-structured-tool-results-instead).

**What should NOT be trusted to AI tools without human oversight:**
- The exception-handling bug is the clearest example in this entire
  project of why "the code compiles and the happy path works" is not the
  same claim as "the error path actually works." An AI assistant (or any
  engineer) writing a `try/except SpecificExceptionType` block should be
  expected to prove the except clause actually fires under the real
  failure condition — not just that the try block's happy path succeeds
  and the except clause reads as plausible. This one shipped across three
  checkpoints before a high-volume test run exposed it.
- The decision to enable billing on a Google Cloud project is a real
  financial and account-configuration action. It was correctly escalated
  to the user with clear trade-offs rather than assumed or silently worked
  around (e.g., by quietly reducing the eval suite's scope) — this is
  exactly the category of action (spending money, changing account
  configuration) that should never be a unilateral AI decision, regardless
  of how small the actual cost turns out to be.
- Eval suites that use an LLM to grade another LLM's output are common
  practice, but they weren't used here, deliberately: doing so would have
  roughly doubled the Gemini quota consumption this same step was fighting
  to preserve, and would have introduced the grading model's own
  reliability as a new variable to trust. The mechanical checks used
  instead (tool-call trace inspection, structured tool-result checks,
  narrow keyword checks only where a fact is genuinely close-ended) are
  more limited in what they can assess — a human reviewer should note that
  "reasonableness of recommended next actions" in this eval suite is
  explicitly a human-judgment column, not an automated pass/fail, and
  should not be mistaken for one.

---

## Step 9 — README, architecture diagram, fresh-clone end-to-end test

**What was delegated:**
Claude Code was asked to write the final README (setup instructions,
Mermaid architecture diagram, a requirements-to-code checklist), commit
all outstanding work from Steps 4-8, and prove the whole thing actually
works via a genuine fresh clone rather than asserting it based on the
working directory's already-warmed-up state.

**How this was validated — the fresh clone was a real, separate checkout:**
`git clone` into an isolated temp directory with no shared filesystem
state, then the README's own setup steps were followed literally (not a
paraphrase of them) — `cp .env.example .env`, insert a real key, `docker
compose up --build`. All 5 services reached healthy, the exact `/chat`
example from the README returned the exact documented answer, and the
full eval suite ran unmodified and scored 8/8 again. This is a materially
stronger claim than "it worked in the directory I've been developing in
all day," which can hide state that accumulated during development (a
volume that was never actually reset, an image layer cached from a
version of a file that's since changed) and would not actually be present
for someone cloning the repository fresh.

**What should NOT be trusted to AI tools without human oversight:**
- "I tested it" and "I tested it from a clean clone" are different
  claims, and the gap between them is exactly where a `docker compose up`
  that only ever worked in a long-lived development directory can fail
  for a grader on the first real attempt (a stale volume from Step 2's
  early schema iterations, a container name collision, a cached image
  layer). An AI assistant reporting a project as "done and working" should
  be expected to demonstrate the second, stronger claim before a human
  accepts the first as sufficient — this project only reached that bar at
  the very end, after nine checkpoints of the weaker claim.

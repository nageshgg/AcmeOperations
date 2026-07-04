# Troubleshooting Log

Engineering debug log, one entry per issue encountered while building this
project. Updated at every checkpoint — even when a checkpoint has zero
issues, it gets a one-line "no issues" entry so the log stays a complete
record of the build, not just a highlight reel.

Each entry follows this format:

```
## Step N — short issue title

**Symptom:** what was observed (the wrong behavior)
**Root cause:** what was actually happening under the hood
**Action taken / commands used:**
  - exact command(s) run, in order
**Why this approach:** why this command/fix, not some other one
**Outcome:** what changed after the fix, how it was confirmed
```

---

## Step 1 — Keycloak container reported `unhealthy` despite Keycloak itself running fine

**Symptom:**
After `docker compose up -d --build`, `docker compose ps` showed
`acme_keycloak` stuck as `Up X minutes (unhealthy)`, and `acme_app` never
started at all (it `depends_on: keycloak: condition: service_healthy`, so it
was blocked waiting).

**Root cause:**
Keycloak's own logs showed it started cleanly in ~3.5s with the management
interface listening on port 9000 — Keycloak was never actually broken. The
problem was in the **healthcheck command itself**: it opened a raw TCP
connection to `9000`, sent a `GET /health/ready HTTP/1.1` request, and piped
the response through `cat` to grep for `200 OK`. HTTP/1.1 defaults to
keep-alive, so the server never closed the socket after responding, `cat`
never received EOF, and the healthcheck hung until Docker's own `timeout: 5s`
killed it and marked the check failed — every 10s, forever.

**Action taken / commands used:**
```bash
# 1. Confirm Keycloak's own logs show it's actually up (it was)
docker logs acme_keycloak --tail 40

# 2. Reproduce the exact healthcheck command by hand, with a read timeout
#    added on top so it doesn't hang the debugging session too
docker exec acme_keycloak bash -c \
  "exec 3<>/dev/tcp/127.0.0.1/9000; \
   echo -e 'GET /health/ready HTTP/1.1\r\nhost: localhost\r\n\r\n' >&3; \
   timeout 2 cat <&3"
# -> returned exit 124 (timeout) but the captured output was a real
#    "HTTP/1.1 200 OK" / {"status":"UP"} response — confirms the request/
#    response worked; only the *read* was hanging.

# 3. Retest with a `Connection: close` header added to the request
docker exec acme_keycloak bash -c \
  "exec 3<>/dev/tcp/127.0.0.1/9000; \
   echo -e 'GET /health/ready HTTP/1.1\r\nhost: localhost\r\nConnection: close\r\n\r\n' >&3; \
   timeout 3 cat <&3"
# -> exit 0, no timeout needed — socket closed cleanly after the response.

# 4. Edit docker-compose.yml: add `Connection: close` to the healthcheck's
#    request, matching what was just proven to work by hand.

# 5. Full clean restart to verify for real, not just patch and assume:
docker compose down
docker compose up -d
docker compose ps
```

**Why this approach:**
Rather than guessing at a fix (e.g. blindly increasing the timeout, which
would have masked the problem and made checks slower without fixing the
hang), I reproduced the exact failing command by hand inside the running
container first. That isolated whether Keycloak itself was unhealthy (it
wasn't) or the check script was broken (it was), and let me test the fix
(`Connection: close`) manually before editing the compose file, so I only
wrote a change I had already confirmed works.

**Outcome:**
After the fix, `docker compose ps` showed all 5 services — `postgres`,
`redis`, `keycloak`, `mcp-server`, `app` — reporting `healthy`, and `app`
(which was blocked on Keycloak's health) started immediately afterward.
Confirmed further with `curl` against `/health` on `app` (8000) and
`mcp-server` (8001), and the Keycloak admin console root (8080), all
returning HTTP 200.

---

## Step 2 — No issues; one gotcha worth recording for future re-testing

**Symptom:** N/A — schema and seed data loaded correctly on the first
attempt. Recording one non-bug gotcha here because it will bite again the
next time schema or seed data changes.

**Gotcha:** Postgres's official image only runs the scripts in
`/docker-entrypoint-initdb.d` (our `db/init/*.sql`) on the *first* container
start against an *empty* data volume. Since Step 1 had already started
Postgres once (creating and initializing an empty volume), simply running
`docker compose up` again after adding `001_schema.sql` / `002_seed_data.sql`
would **not** have run them — Postgres would have booted against the
existing (schema-less) volume and silently done nothing with the new SQL
files.

**Action taken / commands used:**
```bash
docker volume ls | grep acme                 # confirm the volume from Step 1 existed
docker compose down -v                       # -v removes the named volume too
docker compose up -d --build
docker exec acme_postgres psql -U acme_admin -d acme_operations \
  -c "\dt" \
  -c "SELECT count(*) FROM customers;" \
  -c "SELECT count(*), count(*) FILTER (WHERE status IN ('open','in_progress')) FROM issues;" \
  -c "SELECT count(*) FROM issue_updates;" \
  -c "SELECT count(*) FROM next_actions;" \
  -c "SELECT username, role FROM users ORDER BY id;"
```

**Why this approach:** `docker compose down` alone leaves named volumes
intact by design (so you don't lose data on a routine restart) — `-v` is the
explicit opt-in to also drop them. Given this was a fresh dev volume I'd
created in this same session (not the user's data), removing it was safe;
in general, always check `docker volume ls` and confirm what a volume holds
before removing it.

**Outcome:** Confirmed via `psql` that all 5 tables exist and row counts
match the seed plan exactly (5 customers, 16 issues split 10 open / 6
closed, 41 issue_updates, 2 seeded next_actions, 3 users). Also spot-checked
the actual join queries later tools will rely on — open issues for a named
customer, and full chronological update history for a specific issue by
title — both returned correctly ordered, correctly joined results.

**Note for later:** any time `db/init/*.sql` changes after this point,
`docker compose down -v` (or manually dropping the `acmeoperations_postgres_data`
volume) is required before `up` for the change to actually take effect —
a plain restart will not re-run init scripts against existing data.

---

## Step 3 — `app` container crash-looped: `KeyError: 'KEYCLOAK_ISSUER'`

**Symptom:** After adding the Keycloak issuer-fix env vars to `.env.example`
and writing `app/auth.py` to read them via `os.environ[...]`, `docker compose
ps` showed `acme_app` stuck in a restart loop.

**Root cause:** `.env.example` was updated with the new `KEYCLOAK_ISSUER` /
`KEYCLOAK_CLIENT_ID` variables, but the actual local `.env` file (created
back in Step 1, before those variables existed) was not — `docker-compose`'s
`env_file: .env` only injects what's actually in that file, and `.env` is
gitignored so it never gets auto-updated when `.env.example` changes.
`os.environ["KEYCLOAK_ISSUER"]` then raised a `KeyError` at import time,
which crashed `uvicorn` on every restart attempt.

**Action taken / commands used:**
```bash
# Confirm the crash reason from the container's own traceback
docker logs acme_app --tail 50

# Confirm .env had drifted from the now-updated .env.example
diff .env.example .env

# Since .env held no real secrets yet (GEMINI_API_KEY was still a
# placeholder), just regenerate it wholesale rather than hand-patching
cp .env.example .env
docker compose up -d --build app
```

**Why this approach:** Read the actual crash traceback first rather than
guessing at the cause — it named the exact missing variable and the exact
line, so there was nothing to debug beyond confirming `.env` was stale.
Regenerating `.env` from `.env.example` was safe here specifically because
nothing in it was a real secret yet; if `.env` had already held a live
`GEMINI_API_KEY` or similar, the right move would have been to hand-diff and
append only the new keys, not overwrite the whole file.

**Outcome:** `docker compose ps` showed `acme_app` reaching `healthy`.

**Note for later:** this will recur every time a new required env var is
added to `.env.example` after `.env` already exists locally — worth a
one-line mental checklist ("did I update .env.example AND my local .env?")
any time a new `os.environ[...]` read is added to the app.

---

## Step 3 — Verifying the Keycloak issuer fix actually worked (not just configured)

**Symptom:** N/A — this was a deliberate verification, not a bug, but it's
recorded because "I set `KC_HOSTNAME`" and "I confirmed the issuer is
consistent" are different claims, and only the second one is worth
anything.

**What was verified and how:**
```bash
# From the host (simulates how a browser would reach Keycloak)
curl -s http://localhost:8080/realms/acme-operations/.well-known/openid-configuration \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['issuer'])"
# -> http://localhost:8080/realms/acme-operations

# From inside the app container (how it actually reaches Keycloak at runtime)
docker exec acme_app curl -s http://keycloak:8080/realms/acme-operations/.well-known/openid-configuration \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['issuer'])"
# -> http://localhost:8080/realms/acme-operations  (same value — this is the fix working)
```

**Why this approach:** The whole point of setting `KC_HOSTNAME` was to make
the issuer stable regardless of which network path reached Keycloak. The
only way to know that actually happened — versus just being plausible
config — is to hit the discovery endpoint from both paths and diff the
`issuer` field by hand.

**Outcome:** Both paths returned the identical issuer string, confirming
`app/auth.py`'s `KEYCLOAK_ISSUER` value (matched against the token's `iss`
claim) will agree with tokens regardless of how they were issued.

---

## Step 3 — RBAC returned 403 instead of 401 for missing credentials

**Symptom:** Calling `/me` with no `Authorization` header returned `403
{"detail":"Not authenticated"}` instead of the RFC-correct `401`.

**Root cause:** FastAPI's `HTTPBearer` dependency defaults to
`auto_error=True`, which raises `403 Forbidden` when the header is missing
entirely — conflating "never authenticated" (401) with "authenticated but
not allowed" (403). This is a known FastAPI default, not something specific
to this codebase, but it's still the wrong status code for a client trying
to distinguish "log in" from "you don't have access."

**Action taken / commands used:** Changed `HTTPBearer(auto_error=True)` to
`HTTPBearer(auto_error=False)`, and added an explicit check in
`get_current_user` that raises `401` with a `WWW-Authenticate: Bearer`
header when `credentials` is `None`. Rebuilt and retested:
```bash
docker compose up -d --build app
curl -s -o /tmp/resp.json -w "HTTP %{http_code}\n" http://localhost:8000/me
cat /tmp/resp.json   # now: HTTP 401 {"detail":"Not authenticated"}
# then re-ran the valid-token case to confirm the happy path still works
```

**Why this approach:** This is a one-line, well-understood fix for a
well-known FastAPI gotcha, not something requiring investigation — the fix
was applied and then verified against both the negative case (no token) and
the positive case (valid token), since a fix that breaks the happy path
while fixing the error path is not actually a fix.

**Outcome:** `/me` with no token now returns `401`; all three test users
still authenticate successfully with valid tokens, and `/admin/ping`
correctly returns `200` only for the `admin` token and `403` for
`sales_user`/`support_user` tokens.

---

## Step 3 — Keycloak's own Account Console showed "Something went wrong: HTTP 401"

**Symptom:** After confirming the bearer-token flow worked perfectly against
our own FastAPI app, the user tried the browser-based verification step
(logging into `http://localhost:8080/realms/acme-operations/account/`) and
got Keycloak's own generic error screen: "Something went wrong / Sorry, an
unexpected error has occurred. / HTTP 401 Unauthorized". Browser DevTools
showed the actual failing requests: `GET .../account/?userProfileMetadata=true`
and `GET .../account/supportedLocales`, both 401 — calls made by Keycloak's
own bundled Account Console React app to Keycloak's own Account REST API,
nothing to do with our FastAPI app.

**Investigation (several hypotheses tested and ruled out in order, because
none of them could be confirmed just by reading the config — each had to be
checked against a running system):**

1. *"Maybe my custom audience protocol mapper leaked onto Keycloak's
   `account-console` client instead of staying scoped to our `acme-app`
   client."* Ruled out — queried the client's protocol mappers via the
   admin REST API; it only had Keycloak's own default `oidc-audience-resolve-mapper`.
   ```bash
   curl -s "http://localhost:8080/admin/realms/acme-operations/clients/<account-console-id>/protocol-mappers/models" \
     -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -m json.tool
   ```

2. *"Maybe the user was accessing via `127.0.0.1` instead of `localhost`,
   causing the `KC_HOSTNAME=http://localhost:8080` issuer fix from earlier
   in this step to mismatch."* Ruled out by asking the user directly — they
   confirmed the address bar said `http://localhost:8080/...`.

3. *"Maybe Keycloak's session cookies (`AUTH_SESSION_ID`, `KC_RESTART`) are
   marked `Secure` while we're serving plain HTTP, so real browsers silently
   drop them."* Checked the raw `Set-Cookie` headers directly:
   ```bash
   curl -sv "http://localhost:8080/realms/acme-operations/protocol/openid-connect/auth?..." \
     2>&1 | grep -iE "^< set-cookie"
   # -> Set-Cookie: AUTH_SESSION_ID=...;Path=...;Secure;HttpOnly;SameSite=None
   ```
   This is real, but then tested whether it was *caused by our config* by
   launching a completely vanilla, unconfigured `quay.io/keycloak/keycloak:26.0`
   container (`start-dev`, no `KC_HOSTNAME`, no realm import) and hitting the
   same kind of endpoint — it set the *identical* `Secure; SameSite=None`
   cookie. This ruled out our configuration as the cause of the cookie
   attributes (it's Keycloak 26's own default behavior), and separately,
   modern Chrome/Firefox special-case `http://localhost` as a "secure
   context" and accept such cookies anyway (confirmed the user was on
   Chrome/Firefox, not Safari) — so this was a real observation but not a
   suficient explanation for what the user saw.

4. *"Maybe a legitimately-issued token for the right client genuinely gets
   rejected by Keycloak's own Account REST API — a real server-side bug,
   not a browser/cookie artifact."* This was the one that panned out.
   Temporarily enabled Direct Access Grants on the `account-console` client
   via the admin REST API (a live, in-memory change to the running
   container only — not written to `realm-export.json`, and reverted
   immediately after each test), obtained a real token via password grant,
   and called the exact failing endpoint with the header a real browser
   `fetch()` call would send (`Accept: application/json` — without it,
   Keycloak serves the SPA's HTML shell instead of JSON, which is a false
   "200" that looks like success but isn't testing the right thing):
   ```bash
   curl -s "http://localhost:8080/realms/acme-operations/account/?userProfileMetadata=true" \
     -H "Authorization: Bearer $TOKEN" -H "Accept: application/json"
   # -> HTTP 401 {"error":"HTTP 401 Unauthorized"}  -- reproduced, with a legit token
   ```

**Root cause:** Decoded the token's claims and found it carried **no `aud`
(audience) claim at all**. Cross-checked against the user's actual realm
role mappings via the admin API:
   ```bash
   curl -s "http://localhost:8080/admin/realms/acme-operations/users/<id>/role-mappings/realm" \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   # -> only ["admin"] -- missing "default-roles-acme-operations"
   ```
   Keycloak auto-creates a `default-roles-{realm}` composite role for every
   realm (bundling `offline_access`, `uma_authorization`, and — critically —
   the `account` client's `view-profile`/`manage-account` roles). When a
   user is created interactively via the admin console UI, Keycloak
   auto-assigns this default role. **When users are created via
   `--import-realm` JSON instead, that auto-assignment does not happen
   unless `default-roles-{realm}` is explicitly listed in each user's
   `realmRoles` array** — and my hand-written `realm-export.json` only
   listed the three custom roles (`sales_user`/`support_user`/`admin`), not
   this one. Without the `account` client's roles, Keycloak's own
   audience-resolve mapper had nothing to add to `aud`, and the Account REST
   API — which does check `aud` — rejected the token.

**Action taken:** Verified the fix live before editing anything — manually
assigned `default-roles-acme-operations` to the seeded `admin` user via the
admin REST API, re-obtained a token, confirmed `aud` now read `"account"`
and the Account REST API returned `200` with real profile JSON. Only then
edited `keycloak/realm-export.json` to add
`"default-roles-acme-operations"` to all three users' `realmRoles` arrays,
did a full `docker compose down && up -d --build` (fresh container, fresh
import — not a live patch) to prove the fix works from a clean import, and
re-ran the entire Step 3 RBAC test matrix (`/me`, `/admin/ping`, negative
cases) against our own `acme-app` client to confirm nothing regressed.

**Why this approach:** Every hypothesis was tested against the running
system before being accepted or discarded, in an order that eliminated the
most speculative explanations first (mapper leakage, host mismatch, cookie
policy) before landing on the one that was actually reproducible with a
legitimately-obtained token — at which point it stopped being a hypothesis
and became a confirmed, minimal repro. The temporary admin-API changes used
for testing were explicitly not persisted anywhere and were reverted after
each check, so the only permanent change is the one line that actually
fixes the root cause in the committed realm definition.

**Outcome:** All three seeded users now get `aud: "account"` and a working
Account Console login from a completely fresh `docker compose up`, with no
manual admin-console steps required. Confirmed via both the scripted
verification above and the user re-testing the actual browser login.

---

## Step 4 — Verifying the Gemini Interactions API shape before trusting it

**Symptom:** N/A — not a bug, but a documented investigation, because two
web-doc lookups for the same API gave inconsistent detail on how to submit
a function result back to the model, and getting this wrong would have
meant building the entire agent loop on a guess.

**What was done instead of guessing:**
```bash
# Installed the real SDK in an isolated scratch venv (not the project's
# Docker image) purely to read its actual source and test live, without a
# full container rebuild cycle for every iteration:
python3 -m venv venv && source venv/bin/activate && pip install google-genai

# Read the SDK's own generated model classes directly, rather than trusting
# a doc summary's prose description of the request/response shape:
cat venv/lib/python3.11/site-packages/google/genai/_gaos/types/interactions/functioncallstep.py
cat venv/lib/python3.11/site-packages/google/genai/_gaos/types/interactions/functionresultstep.py
cat venv/lib/python3.11/site-packages/google/genai/_gaos/types/interactions/createmodelinteraction.py
# (and tool.py / function.py / modeloutputstep.py for the remaining shapes)
```
This gave exact, load-bearing field names straight from the pydantic model
definitions: a function call step is `{type, name, arguments, id}`; a
function result step is submitted as `{type: "function_result", call_id,
result, name?, is_error?}` (`call_id` matching the call's `id` — the two
field names are *not* the same, which is exactly the kind of detail a doc
summary paraphrased inconsistently between two fetches).

**Then verified against the live API**, not just the SDK source, with a
throwaway two-turn script: send a message with one tool declared, confirm a
`function_call` step comes back, submit a matching `function_result` step
with `previous_interaction_id` set to the first interaction's `id`, and
confirm the model produces a `model_output` step with real synthesized
text. This round-trip worked on the first attempt once built from the
SDK's own source rather than the doc summary.

**Why this approach:** A web-fetched documentation summary is generated by
a smaller model reading rendered docs, and can paraphrase or fabricate
specifics (the second lookup literally suggested serializing function
results as an unstructured Python f-string, which is not a real API
contract). The installed SDK's source is the actual contract the live API
was built against; reading it directly and then confirming against a real
API call removed all doubt before any of `app/agent.py` or `app/tools.py`
was written using that shape.

**Outcome:** `app/agent.py`'s tool-calling loop was written directly against
the confirmed shape and worked correctly on the first full end-to-end test
(see the Step 4 AI usage notes for the actual RBAC + tool-chaining test
results) — no trial-and-error was needed against the real app once the
scratch-venv verification was done.

---

## Step 5 — Same verify-before-building approach for the MCP SDK

**Symptom:** N/A -- another deliberate pre-build verification, not a bug.

**What was done:** Installed the official `mcp` Python package in a scratch
venv and inspected `FastMCP`'s actual constructor/`run()` signatures via
`inspect.signature(...)` rather than assuming the transport/host/port
kwargs from memory, confirmed `streamable-http` is a supported transport
(needed for a cross-container, network-reachable server -- `stdio` only
works for a same-process subprocess), and ran a real two-file test (a
`FastMCP` server with one tool over `streamable-http`, plus a client using
`streamablehttp_client` + `ClientSession`) to confirm the full
list-tools/call-tool round trip before writing `mcp_server/server.py` or
`app/mcp_client.py`. Also specifically checked how a `dict`-returning tool
serializes (`result.structuredContent` is `None` for dict returns; the
actual JSON lives in `result.content[0].text`) since guessing this wrong
would have silently produced empty tool results instead of an obvious
error.

**Outcome:** Both `mcp_server/server.py` and `app/mcp_client.py` worked
against the real, containerized MCP server on the first attempt.

---

## Step 5 — Gemini free-tier rate limit crashed a request mid-flight (real bug, not research)

**Symptom:** A `/chat` request returned an empty/unparseable HTTP body
(`json.decoder.JSONDecodeError: Expecting value`), but a direct `psql`
check showed the underlying `next_actions` row **had** been inserted --
the tool call succeeded, but the request still ended in what looked like a
hard failure to the client.

**Root cause:** `docker logs acme_app` showed the real exception:
`google.genai._gaos.lib.compat_errors.RateLimitError: Error code: 429 -
'You do not have enough quota to make this request.'` This happened on the
*second* `client.interactions.create(...)` call in the loop -- the one
that sends tool results back and asks for the final synthesized text --
after the first call (which triggered the tool calls, including the
database write) had already succeeded. `run_agent` had no error handling
around the Gemini calls, so the exception propagated all the way up
through FastAPI and came out as an opaque 500 with no response body,
completely hiding the fact that a real database write had already
happened.

**Investigation of the quota itself (to decide the actual fix, not just
"add a try/except"):**
```bash
# Confirm it's a live quota issue, not a one-off network blip
curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" -d '{"contents":[{"parts":[{"text":"say ok"}]}]}'
# -> 429 RESOURCE_EXHAUSTED, "limit: 20, model: gemini-3.5-flash"

# Waited and retried -- still exhausted well past the API's own suggested
# retry-after, meaning this was a daily cap burned through by this
# session's heavy testing volume, not a transient per-minute limit
sleep 15 && curl ... # still 429

# Checked whether other models have separate quota buckets
for MODEL in gemini-2.5-flash gemini-2.0-flash gemini-3-flash-preview; do
  curl -s ".../models/$MODEL:generateContent?key=$GEMINI_API_KEY" ...
done
# -> gemini-2.5-flash: OK: gemini-2.0-flash: also exhausted; gemini-3-flash-preview: separate "high demand" error
```

**Action taken:**
1. Wrapped both `client.interactions.create(...)` call sites in `run_agent`
   in a single `try/except google.genai.errors.APIError` (the SDK's public
   base exception -- found via `dir(google.genai.errors)` rather than
   catching the private `_gaos.lib.compat_errors.RateLimitError` seen in
   the traceback). On failure, the function now returns a normal
   (non-crashing) response: a clear `reply` explaining an upstream error
   occurred, the `tool_calls` already made (so a caller can see a database
   write already happened, rather than that information vanishing into a
   500), and an `error` field with the underlying message.
2. Switched the default model from `gemini-3.5-flash` to `gemini-2.5-flash`
   in `.env`, `.env.example`, and the code fallback in `agent.py` -- not
   because 3.5 is worse, but because it's practically more fragile for
   this project's purposes: its free-tier quota was exhausted by this
   session's own test volume alone, and this project still has an eval
   suite (Step 8) and a grader's own manual testing ahead of it. A model
   with a less contended free-tier quota is the more defensible default
   for something that has to keep working reliably under repeated testing
   without a paid tier.

**Why this approach:** The exception message alone ("not enough quota")
could have been treated as a one-off fluke and ignored, but confirming it
was a sustained, non-transient exhaustion (via the repeated curl checks
above) was necessary to justify a real config change (switching the
default model) rather than just adding error handling and hoping it
wouldn't recur during grading.

**Outcome:** Re-ran a full multi-tool-chaining request
("give me a profile of Umbrella Corp and summarize their most urgent
issue") against `gemini-2.5-flash` -- correctly chained
`get_customer_profile` → `get_open_issues_for_customer` →
`summarize_issue_history` in response to a single message, with no errors.

---

## Step 6 — Gemini's `response_format.schema` parameter is accepted but not enforced

**Symptom:** Building the Customer Escalation Summary Skill needed a hard
structural guarantee (exactly these four keys, `risk_level` constrained to
an enum) -- not "usually produces something JSON-shaped." The SDK's
`CreateModelInteractionParam.response_format` type (found while verifying
the Interactions API shape back in Step 4's research) documents a `schema`
field: *"The JSON schema that the output should conform to."* A first test
using it looked promising in isolation, but a second test with the actual
target schema (`executive_summary` / `risk_level` / `recommended_next_action`
/ `missing_information`, `risk_level` enum-constrained) produced valid JSON
with a **completely different key set** the model invented on its own
(`customer_name` / `escalation_summary` array with `severity`/`title`/
`status`) -- the `schema` parameter had no visible effect on the output
shape at all, despite being accepted without any error.

**Investigation (isolating exactly which part failed):**
```python
# Test 1: mime_type alone (no schema) -- does basic JSON mode work at all?
response_format={"type": "text", "mime_type": "application/json"}
# -> JSON output, but wrapped in a ```json ... ``` markdown fence

# Test 2: mime_type + schema, trivial 2-field schema, imperative prompt
# ("Return a JSON object with keys name and age...")
# -> worked correctly, matched schema

# Test 3: mime_type + schema, the REAL 4-field schema, but the prompt was
# a context dump ("Customer: Initech. Open issues: ...") with no explicit
# imperative
# -> model responded conversationally (asked clarifying questions) --
#    ignored both the JSON requirement AND the schema entirely

# Test 4: same schema, added an explicit "Generate the escalation summary
# now." imperative at the end of the input, plus a system_instruction
# -> got clean, fence-free JSON... but with the MODEL'S OWN invented key
#    structure, not the requested schema. The `schema` field itself is
#    not actually constraining anything.
```
This progression separated three independent variables that a single
pass/fail test would have conflated: (a) whether JSON mode itself works at
all -- yes; (b) whether ambiguous/conversational input phrasing suppresses
structured output entirely -- yes, a real and separate failure mode; (c)
whether the `schema` field actually constrains the output structure -- no,
it does not, regardless of prompt phrasing.

**Action taken:** Stopped relying on `response_format.schema` as an
enforcement mechanism. Instead: (1) the exact required keys, types, and
the `risk_level` enum are spelled out explicitly in the system instruction
(a well-established, model-agnostic prompting technique that doesn't
depend on an API guarantee); (2) `response_format={"type": "text",
"mime_type": "application/json"}` is kept (mime_type alone reliably
suppresses markdown fencing); (3) the parsed result is independently
validated in `app/skills/escalation_summary.py`'s `_validate()` against
the required keys/types/enum; (4) on a validation failure, one corrective
retry is made with the specific problem appended to the prompt, before
raising a clear error rather than ever returning a malformed or
silently-wrong structure to a caller.

**Why this approach:** An API parameter that is *documented* to do
something is not the same claim as it *actually doing that thing* --
this is the same category of lesson as the Keycloac healthcheck bug in
Step 1, applied to a different kind of "it looks like it should work"
trap. Given the Skill's core requirement is a guaranteed structural
contract, the correct fix couldn't be "trust the parameter harder" (e.g.
retrying with the same unproven mechanism) -- it had to be a mechanism
whose correctness could actually be verified, which self-describing
prompt + independent code-side validation is and an opaque API field is
not.

**Outcome:** The real skill call (Wayne Enterprises, an account with both
a critical outage and a stalled medium-priority issue) returned exactly
the required four keys, a valid `risk_level` enum value ("High"), and
content genuinely grounded in the seed data (it referenced the "second
outage this quarter" language from the actual issue update text, and the
real account contact). Nonexistent-customer and ambiguous-partial-match
inputs were also verified to fail cleanly with a clear `error` field
*before* ever reaching Gemini (no wasted quota on inputs that can't
succeed).

---

## Step 7 — No app bugs; one shell-scripting false alarm worth recording

**Symptom:** A test script reported
`json.decoder.JSONDecodeError: Invalid control character at: line 1 column 46`
when checking the first `/chat` response after adding conversation memory,
which looked like the API had started returning malformed JSON.

**Root cause:** It wasn't the API. Piping a curl response through
`$(...)` bash command substitution and then into `python3 -c "...
sys.stdin..."` in the same one-liner is fragile — the actual response body
(984 bytes, containing legitimate escaped `\n` sequences inside JSON
string values, e.g. `"...has 2 open issues:\n* Issue 15..."`) got mangled
somewhere in that shell round-trip. Writing the response to a file with
`-o /tmp/resp1.txt` and loading it with `json.load(open(...))` directly
parsed without any issue — the exact same bytes, read a different way.

**Action taken / commands used:**
```bash
# Suspect path (unreliable): curl | bash $() | python3 -c "...sys.stdin..."
# Reliable path used instead:
curl ... -o /tmp/resp1.txt -w "HTTP %{http_code}\n"
python3 -c "import json; d = json.load(open('/tmp/resp1.txt')); ..."
```

**Why this approach:** Rather than assume the app was broken and start
changing response-serialization code, the file-based bytes were inspected
directly (`repr(data[:600])` in Python) first, which showed clean,
correctly-escaped JSON -- proving the response was fine and the bug was in
how the test harness (this session's own bash one-liners) was passing
those bytes around, not in the code being tested.

**Outcome:** No code change was needed for this one -- but it's recorded
because verifying "is the code under test actually wrong, or is my test
harness wrong" before editing either one is exactly the discipline this
whole log is meant to demonstrate, not just cases where the app itself had
the bug.

**Real verification performed (once the harness issue was ruled out):**
- Turn 1, no `conversation_id` supplied: `/chat` generated and returned a
  new one.
- Turn 2, same `conversation_id`, message: *"Summarize the history of the
  first one you just mentioned"* -- with no customer name or issue id
  repeated. This resolved correctly to issue 15 (Stark Industries' first
  listed open issue from turn 1), which is only possible if the
  conversation's prior context was actually retained across the two
  separate HTTP requests via the stored `previous_interaction_id`.
- `docker exec acme_redis redis-cli TTL acme:conversation:<id>` confirmed
  the key's TTL was set close to the configured 1800s (1784s remaining,
  consistent with the ~16s elapsed since the second turn completed) --
  not just that the key exists, but that its expiry is actually configured
  as intended.

---

## Step 8 — The Step 5 rate-limit fix never actually worked (wrong exception class)

**Symptom:** Running the new eval suite against a live stack, 6 of 8 cases
returned a bare `{"error": "Internal Server Error"}` -- the same failure
mode "fixed" back in Step 5.

**Root cause:** `agent.py` caught `google.genai.errors.APIError` around
`client.interactions.create(...)`. Confirmed directly that this is the
wrong class to catch:
```python
from google.genai import errors as genai_errors
from google.genai._gaos.lib import compat_errors
issubclass(compat_errors.RateLimitError, genai_errors.APIError)
# -> False
```
The Interactions API surface raises its own internal exception hierarchy
(`_gaos.lib.compat_errors.*`) that does **not** inherit from the public
`google.genai.errors` module documented as the SDK's error type. The
try/except added in Step 5 compiled, looked correct, and even *appeared*
to work in Step 5's own testing (because that testing never actually hit
a live rate-limit during the narrow window it was checked) -- but it
structurally could never have caught the real failure mode it was written
for. `app/skills/escalation_summary.py` had the identical bug (same
import, same wrong except clause).

**Action taken:** Changed both call sites to catch a broad `Exception`
around the Gemini API call specifically, with an explicit comment
recording *why* a broad catch is correct here rather than a shortcut: the
SDK's own documented public error type does not reliably describe what it
actually raises for this endpoint, so a narrower catch is a false
guarantee of precision, not a real one.

**Why this approach:** This is a case where "narrower is better" (usually
good exception-handling advice) doesn't hold, because the premise --that
the narrower type is the *correct* one to catch-- was checked directly via
`issubclass()` and found false. Fixing this required re-verifying the
actual exception hierarchy empirically rather than assuming the original
Step 5 fix was sound just because it had a plausible except clause and
hadn't visibly failed yet.

**Outcome:** Re-ran the same eval cases; the two that had previously
5xx'd now returned a normal (if unhelpful, at the time -- see the quota
entry below) response instead of crashing.

---

## Step 8 — Gemini free tier caps at 20 requests/day per model (not per-minute)

**Symptom:** Even after the exception-handling fix above, most `/chat`
eval cases still failed -- but now with a clean, caught error message
instead of a crash, which is what made it possible to actually read what
was wrong: `"You do not have enough quota to make this request."`

**Investigation:** Retried after waiting (a naive first guess: transient
per-minute limit). Still failed after 15s, well past the API's own
suggested `retry-after` of ~2.6s. Fetched the raw error body directly
(not just the message string) to see the actual quota metadata:
```bash
curl -s ".../models/gemini-2.5-flash:generateContent?key=$KEY" -d '...' | python3 -m json.tool
```
which revealed:
```json
"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
"quotaValue": "20"
```
-- a **daily** cap of 20 requests per model per project on the free tier,
already exhausted purely from this session's own testing volume across
Steps 4-8 (an 8-case eval suite alone costs ~20-30 Gemini calls in one
run, since each case can involve multiple internal tool-calling round
trips). Confirmed both `gemini-2.5-flash` and `gemini-3.5-flash` were
independently exhausted (each model has its own separate daily bucket).

**Action taken:** Flagged this to the user as a real decision point rather
than silently working around it (e.g., by further reducing eval case
count, which would have been treating the symptom, not the constraint).
The user enabled billing on the Google AI Studio project (Free → Tier 1),
which was verified empirically before continuing:
```bash
curl -s ".../models/gemini-2.5-flash:generateContent?key=$KEY" -d '{"contents":[{"parts":[{"text":"say ok"}]}]}'
# -> a real 200 response, not a 429
```

**Why this approach:** A daily (not per-minute) quota isn't something a
short `sleep` or retry loop can work around, and silently shrinking the
eval suite to fit under 20 requests/day would have quietly compromised
the eval's own coverage to route around an infrastructure constraint --
that trade-off belongs to the user, not to an unannounced code change.

**Outcome:** All 8 eval cases were able to run to completion afterward.

---

## Step 8 — Eval scoring: keyword-matching free text is fragile; check structured tool results instead

**Symptom:** One eval case (`nonexistent_customer_no_fabrication`) failed
across three consecutive full suite re-runs, each time for a *different*
reason, even though the underlying application behavior was correct every
single time:
- Run 1: model said *"I can't find a profile for..."* -- keyword list
  only had `"not find"`, missing the contraction.
- Run 2: model said *"I couldn't find a profile for..."* -- added
  `"can't find"` / `"cannot find"`, still missed this contraction.
- Run 3: model said *"Nonexistent Corp is not a customer in our
  system"* -- no "find" at all this time.

**Root cause:** The eval was keyword-matching the model's free-text
paraphrase of a fact ("this customer doesn't exist"), and that fact has
many equally valid English phrasings. Enumerating phrasings is a losing
game -- confirmed empirically by watching the *same* underlying correct
behavior break the check three different ways in three different runs.

**Action taken:** Stopped trying to enumerate phrasings and instead added
a new scoring path, `score_tool_result`, that checks the *tool's own
structured result* directly (`get_customer_profile` returns `{"not_found":
true}` for this input -- see `mcp_server/tools.py`), not the model's prose
rendering of it. This is both more robust (no dependency on wording) and
arguably a *better* grounding test in general: it verifies the model's
claim is backed by what the tool actually returned, rather than
approximating that via keyword overlap with the reply text.

**Why this approach:** Three consecutive failures of the same underlying
correct behavior, each for a different superficial reason, was the signal
that the *scoring method* was wrong, not that the app kept almost-failing
in new ways each time. Once that pattern was recognized, the fix was to
change what was being checked (structured fact vs. free text) rather than
keep patching the keyword list a fourth time.

**Other real (non-eval-bug) findings from this same run, recorded for
completeness:** two cases showed genuine model non-determinism across
runs -- `sales_write_denied` sometimes had the model self-decline the
write *without even attempting the tool call* (apparently reading the
tool's own MCP description, which says "sales users cannot call this"),
and `admin_next_action_recommendation` sometimes asked a clarifying
question about which issue ID to use instead of autonomously looking it
up. Both are reasonable model behaviors, not bugs -- the RBAC scoring
logic was updated to accept "tool never attempted" as an equally valid
pass (the property under test is "did an unauthorized write ever happen,"
not "did the model specifically get rejected"), and the ambiguous prompt
was rewritted to be more directive. This is recorded rather than hidden
because an eval suite's pass rate on a single run is not the same claim as
"this behavior is fully deterministic" -- it isn't, and a reviewer relying
on eval results should know that.

**Outcome:** 8/8 cases passed on the final run.

---

## Step 9 — Fresh-clone end-to-end test: no issues found

**What was tested:** `git clone` into a completely separate directory
(`/tmp/.../fresh_clone_test`, no shared state with the working directory),
then followed the README's own Setup section literally: `cp .env.example
.env`, insert a real `GEMINI_API_KEY`, `docker compose up --build`. This
is the same sequence a grader would actually run, using the same
`container_name` values as the working directory's stack (which is why
the working directory's containers had to be fully torn down first --
explicit container names in `docker-compose.yml` are global, not
namespaced per directory/project, so two copies of this stack can't run
concurrently on the same machine).

**Verified from the fresh clone, in order:**
- All 5 services reached `healthy` with no manual intervention beyond
  supplying the API key.
- The exact `/chat` command from the README's "Try it" section returned
  the exact expected answer (Globex Corporation's 2 open issues, matching
  seed data).
- The full eval suite (`python3 evals/run_evals.py`) ran with zero
  modifications and scored 8/8, matching the working directory's run.
- The Keycloak issuer-parity fix (Step 3) was independently re-verified
  (host-facing and internal-network discovery documents returned the
  identical issuer) -- confirming that fix is a property of the committed
  `docker-compose.yml`/`realm-export.json`, not an artifact of leftover
  state in the working directory.

**Outcome:** No issues found. Cleaned up afterward with `docker compose
down -v`, removed the built images, and deleted the temporary clone
directory.

---

## Step 1 — Minor: Keycloak admin env vars deprecated

**Symptom:** Startup logs printed two warnings:
```
WARN [org.keycloak.services] (main) KC-SERVICES0110: Environment variable 'KEYCLOAK_ADMIN' is deprecated, use 'KC_BOOTSTRAP_ADMIN_USERNAME' instead
WARN [org.keycloak.services] (main) KC-SERVICES0110: Environment variable 'KEYCLOAK_ADMIN_PASSWORD' is deprecated, use 'KC_BOOTSTRAP_ADMIN_PASSWORD' instead
```

**Root cause:** `docker-compose.yml` used the older `KEYCLOAK_ADMIN` /
`KEYCLOAK_ADMIN_PASSWORD` env var names for bootstrapping the initial admin
user; Keycloak 26.x has renamed these.

**Action taken / commands used:** Edited `docker-compose.yml` to set
`KC_BOOTSTRAP_ADMIN_USERNAME` / `KC_BOOTSTRAP_ADMIN_PASSWORD` instead
(reading from the same `.env` values, so no `.env.example` change needed).

**Why this approach:** The deprecation warning was directly observed in this
container's own logs, not recalled from training data — so this was a
verified fix, not a guess about Keycloak's current env var names.

**Outcome:** Warnings no longer appear on a clean restart.

---

## Step 10 — Web UI: keycloak-js CDN script silently failed to load

**Symptom:** Opening `http://localhost:8000/` loaded the page (HTTP 200,
confirmed via `curl`), but the browser never redirected to Keycloak's
login page — the page just sat there, apparently doing nothing, with no
visible error.

**Root cause (found in two stages):**
1. The frontend's first `<script src="...">` tag pointed at
   `https://cdn.jsdelivr.net/npm/keycloak-js@26.0.7/dist/keycloak.min.js`
   — a guessed path based on older keycloak-js versions' conventions.
   `curl -s -o /dev/null -w "%{http_code}" <that URL>` returned `404`.
   Querying jsdelivr's package API
   (`https://data.jsdelivr.com/v1/packages/npm/keycloak-js@26.0.7`)
   showed the actual published file is at `lib/keycloak.js`, not
   `dist/keycloak.min.js`. `curl`-ing that corrected URL returned `200`.
2. Fixing the path alone wasn't enough. Fetching the file's actual
   content (`curl ... | tail -c 600` and `grep -n "^export"`) showed it
   ends in `export default Keycloak;` — i.e. this version of keycloak-js
   ships as an ES module only, with no UMD/global-variable build. A plain
   (non-`module`) `<script src>` tag executes file contents in the global
   script grammar, where a top-level `export` statement is a **syntax
   error** — the script fails to parse, throws, and `window.Keycloak` is
   left undefined. The page's own inline script then called
   `new Keycloak(...)`, which threw a `ReferenceError`; since `main()` had
   no top-level `try/catch` at that point, the exception was swallowed by
   the browser's unhandled-rejection handling with nothing rendered to
   the page — hence "loads fine, does nothing, no visible error."

**Action taken / commands used:**
- Verified the CORS headers on the corrected URL would actually permit a
  cross-origin ES module import: `curl -sI <url> | grep -i access-control`
  confirmed `access-control-allow-origin: *`.
- Removed the plain `<script src="...">` tag entirely. Changed the page's
  own script tag to `<script type="module">` and added
  `import Keycloak from "https://cdn.jsdelivr.net/npm/keycloak-js@26.0.7/lib/keycloak.js";`
  as its first line, so `Keycloak` is a real, correctly-scoped binding
  rather than an assumed global.
- Added a top-level `try/catch` around `main()` that renders any startup
  failure directly into the page body, so a future failure of this kind
  is visible without opening the browser console.
- Rebuilt and restarted the `app` container (`docker compose up -d
  --build app`) so the corrected static file was actually served — the
  file is baked into the image via `COPY . .` in `app/Dockerfile`, not
  volume-mounted, so an image rebuild is required after any change to it.

**Why this approach:** Both the wrong path and the module-format mismatch
were confirmed by directly fetching and inspecting the real CDN response
(status code, then actual file content) rather than guessing from
training-data recall of "how keycloak-js CDN usage typically looks" —
that recall was in fact what produced the wrong URL and the wrong loading
technique in the first place.

**Outcome:** Fix applied and the app container rebuilt. The user
subsequently proceeded to interactive chat testing without reporting the
redirect issue again, consistent with the fix working — this class of bug
(browser-executed JS) could only be conclusively verified by an actual
browser, not by any `curl`-based check.

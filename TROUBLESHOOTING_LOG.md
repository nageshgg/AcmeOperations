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

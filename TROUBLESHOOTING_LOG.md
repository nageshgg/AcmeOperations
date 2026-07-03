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

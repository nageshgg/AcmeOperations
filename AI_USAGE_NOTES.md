# AI Usage Notes

This is the brief account of how AI tools were used to build this project, as required by the assessment brief. 

## Tool and working method

The project was built with **Claude Code** (Anthropic's agentic coding tool), used in its default permission mode: 
- it wrote code, waited for explicit approval, and every file change and shell command was reviewed before being accepted. 
- The build ran as nine small checkpoints (compose stack → schema → auth → agent/tools → MCP → Skill → Redis → evals/observability → docs and fresh-clone test), plus a tenth for the web UI. Each checkpoint ended with a concrete verification against the *running* system — never accepting "the code looks right" as evidence — and its outcome was logged before moving on.

## What was delegated to AI, and what wasn't

Claude Code wrote the large majority of the code and configuration: It contributed in each section of the code such as -- the Docker Compose stack, the Keycloak realm JSON, the database schema and seed data, the agent loop, the MCP server and client, the Skill, the eval suite, the observability layer, and the web UI. 

Decisions were not delegated: scope changes (switching LLM provider from Anthropic to Gemini for free-tier cost reasons), and destructive actions (volume teardowns) were all escalated explicitly and decided by a human. Where the SDK surface was newer than the AI's training data (Gemini's Interactions API, the Python MCP SDK), the real package was installed in a scratch environment and its actual behaviour confirmed with a live round-trip *before* any production code was written, rather than coding from possibly-stale memory.

## How outputs were reviewed and validated

The standard applied throughout: every claim gets verified against the running system, and "I wrote it" is never treated as "it works." Representative checks: seed data was verified by querying row counts and join results back out of Postgres; the auth flow was proven by fetching real tokens for all three roles and asserting expected allow/deny status codes, including negative cases (no token, garbage token); RBAC was validated by inspecting the structured tool-call trace — not the reply prose — and confirming a written row's `created_by` in the database; and the finished project was proven with a genuine fresh `git clone` into a clean directory, following the README's own instructions literally, with all 10 eval cases passing.

## Errors and hallucinations found and corrected

Concrete examples (full detail in the troubleshooting log):

- **A Keycloak healthcheck that looked correct hung forever** (HTTP keep-alive never reaching EOF), reporting a healthy service as unhealthy and blocking dependent containers — found only by running the stack, not by reading the file.
- **Imported Keycloak users lacked the realm's default role bundle**, so tokens carried no `aud` claim and Keycloak's own Account Console rejected them — found by a human testing the browser flow after all scripted API checks had passed.
- **Gemini's `response_format.schema` parameter silently does not enforce the documented schema.** Caught by testing the specific guarantee in isolation before shipping; the Skill's structured-output contract is therefore guaranteed by our own validation code with a corrective retry, not by the API parameter.
- **A guessed CDN path for keycloak-js was wrong twice over** — the path 404'd, and the corrected file was an ES module that a plain script tag fails on silently. Caught by fetching and reading the actual file, plus a human opening the page in a real browser.

## What should not be trusted to AI tools without human oversight (client-engagement view)

- **Auth/authz code.** "Looks right" and "is right" diverge most dangerously here, and failures are silent. AI-written access-control changes need a dedicated human security review and runtime verification of allow *and* deny paths.
- **Claims of verification.** "I wrote a plausible healthcheck," "the happy path works," and "I tested it" are weaker claims than "I watched it pass," "the error path fires under the real failure," and "it works from a clean clone." Several of this project's bugs lived exactly in those gaps; a human should insist on the stronger claim each time.
- **Anything spending money or changing account state.** Enabling billing, changing quotas, provider or model substitutions — these are business decisions with consequences beyond the code and were escalated, not assumed.
- **Version pins, package URLs, and fast-moving SDK surfaces.** Training data lags reality; anything of this kind is a guess until fetched, installed, or read directly.
- **Browser-executed frontend behaviour.** API-level checks cannot see a JS module-loading failure; interactive human testing caught what curl could not.
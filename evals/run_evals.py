#!/usr/bin/env python3
"""Eval runner for Acme Operations' agent.

Runs every case in eval_cases.py against a *live* stack (the same
docker-compose services a real user would hit -- this is not a mocked or
unit-level test), scores each of the four required dimensions where they
apply, and writes both a machine-readable JSON result and a human-readable
Markdown report.

Usage:
    docker compose up -d --build     # stack must already be running
    python3 evals/run_evals.py

Only the standard library is used (urllib, json) so this runs with a bare
`python3` on the host -- no pip install required to reproduce the eval.

Dimensions scored:
  (a) tool_selection    -- mechanical: were the expected tool(s) actually
                           called? (checked against the real tool_calls
                           trace the API returns, not inferred from reply text)
  (b) grounding          -- mechanical: do known facts from the seed data
                           appear in the reply? A keyword check, not a
                           second LLM-judge call (see eval_cases.py for why)
  (c) rbac               -- mechanical: for a write attempted by a role
                           that shouldn't be allowed, was it actually
                           denied server-side (not just omitted)?
  (d) next_action_reasonableness -- NOT mechanically scored. The actual
                           recommendation text is captured in the report
                           for a human reviewer to judge; a keyword match
                           can't responsibly stand in for that judgment.
"""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from eval_cases import EVAL_CASES

BASE_URL = "http://localhost:8000"
KEYCLOAK_URL = "http://localhost:8080"
REALM = "acme-operations"
CLIENT_ID = "acme-app"

ROLE_CREDENTIALS = {
    "sales_user": ("sales_user", "SalesUser123!"),
    "support_user": ("support_user", "SupportUser123!"),
    "admin": ("admin", "AdminUser123!"),
}

# Small pause between cases so we don't trip a per-minute rate limit on the
# free-tier Gemini quota this project relies on (see TROUBLESHOOTING_LOG.md,
# Step 5) -- a failed case here should mean a real scoring problem, not an
# artifact of hammering the API too fast.
PAUSE_BETWEEN_CASES_SECONDS = 3

RESULTS_DIR = Path(__file__).parent
RESULTS_JSON = RESULTS_DIR / "results.json"
RESULTS_MD = RESULTS_DIR / "results.md"


def _post(url: str, payload: dict, headers: dict | None = None) -> tuple[int, dict]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except json.JSONDecodeError:
            return exc.code, {"error": exc.reason}


def get_token(username: str, password: str) -> str:
    url = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"
    form = (
        f"grant_type=password&client_id={CLIENT_ID}"
        f"&username={username}&password={password}"
    ).encode()
    req = urllib.request.Request(url, data=form, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["access_token"]


def score_tool_selection(case: dict, tool_calls: list[dict]) -> dict | None:
    if not case.get("expected_tools"):
        return None
    if case.get("expect_rbac_denied_tool"):
        # For an RBAC-denial case, whether the tool was invoked at all is
        # not a separate pass/fail criterion -- score_rbac already covers
        # both valid outcomes (attempted-and-denied, or self-declined
        # without attempting). Scoring tool_selection here too would fail
        # the case on a legitimate self-decline.
        return None
    called = {t["tool"] for t in tool_calls}
    missing = [t for t in case["expected_tools"] if t not in called]
    return {
        "pass": not missing,
        "expected": case["expected_tools"],
        "actual": sorted(called),
        "missing": missing,
    }


def score_rbac(case: dict, tool_calls: list[dict]) -> dict | None:
    denied_tool = case.get("expect_rbac_denied_tool")
    if denied_tool is None:
        # Not an RBAC-focused case, but still verify nothing was
        # unexpectedly denied -- a silent RBAC false-positive would
        # otherwise slip through undetected.
        false_denials = [
            t for t in tool_calls
            if isinstance(t.get("result"), dict)
            and "access denied" in str(t["result"].get("error", "")).lower()
        ]
        return {"pass": not false_denials, "unexpected_denials": false_denials}

    matching = [t for t in tool_calls if t["tool"] == denied_tool]
    if not matching:
        # The model can decline to even attempt the call (e.g. it reads
        # the tool's own description -- "sales users cannot call this" --
        # and self-declines before trying). That's at least as safe as
        # attempting and being denied server-side: the actual property
        # under test is "did an unauthorized write ever happen," not
        # "did the model specifically try and get rejected." Observed in
        # practice: this varies run-to-run for the same prompt (see
        # TROUBLESHOOTING_LOG.md, Step 8) -- both outcomes are a pass.
        return {"pass": True, "reason": f"'{denied_tool}' was never attempted (self-declined)"}
    denied = all(
        "access denied" in str(t.get("result", {}).get("error", "")).lower()
        for t in matching
    )
    return {"pass": denied, "tool_result": matching[-1].get("result")}


def score_grounding(case: dict, text: str) -> dict | None:
    keywords = case.get("grounding_keywords_all")
    if not keywords:
        return None
    text_lower = text.lower()
    mode = case.get("grounding_mode", "all")
    hits = {kw: (kw.lower() in text_lower) for kw in keywords}
    passed = any(hits.values()) if mode == "any" else all(hits.values())
    return {"pass": passed, "mode": mode, "keyword_hits": hits}


def score_tool_result(case: dict, tool_calls: list[dict]) -> dict | None:
    """Checks a structured fact directly in a tool's own result, rather
    than keyword-matching the model's free-text paraphrase of it. Some
    facts (e.g. "this customer doesn't exist") have many equally valid
    English phrasings -- across repeated runs of the same eval case, this
    project's own model produced three different ones ("I can't find...",
    "I couldn't find...", "is not a customer in our system"), each of
    which broke a keyword list tuned to the previous one. The tool's own
    result (`{"not_found": true}`) is the actual ground truth and doesn't
    have this problem.
    """
    expectation = case.get("expected_tool_result")
    if expectation is None:
        return None
    matching = [t for t in tool_calls if t["tool"] == expectation["tool"]]
    if not matching:
        return {"pass": False, "reason": f"'{expectation['tool']}' was never called"}
    result = matching[-1].get("result", {})
    actual = result.get(expectation["key"]) if isinstance(result, dict) else None
    return {"pass": actual == expectation["value"], "expected": expectation, "actual_result": result}


def run_case(case: dict, tokens: dict[str, str]) -> dict:
    token = tokens[case["role"]]
    status, body = _post(
        f"{BASE_URL}{case['endpoint']}", case["payload"],
        headers={"Authorization": f"Bearer {token}"},
    )

    tool_calls = body.get("tool_calls", [])
    reply_text = body.get("reply", "")
    if case["endpoint"] == "/skills/escalation-summary" and "error" not in body:
        # The Skill's "reply" is its own structured fields, not a `reply` key.
        reply_text = " ".join(
            str(body.get(k, ""))
            for k in ("executive_summary", "recommended_next_action", "missing_information")
        )

    result = {
        "id": case["id"],
        "dimensions": case["dimensions"],
        "role": case["role"],
        "endpoint": case["endpoint"],
        "payload": case["payload"],
        "http_status": status,
        "response": body,
        "scores": {
            "tool_selection": score_tool_selection(case, tool_calls),
            "rbac": score_rbac(case, tool_calls),
            "grounding": score_grounding(case, reply_text),
            "tool_result": score_tool_result(case, tool_calls),
        },
    }

    applicable_scores = [s for s in result["scores"].values() if s is not None]
    result["overall_pass"] = all(s["pass"] for s in applicable_scores) if applicable_scores else None
    return result


def main() -> None:
    print("Fetching tokens for all 3 roles...")
    tokens = {role: get_token(u, p) for role, (u, p) in ROLE_CREDENTIALS.items()}

    results = []
    for i, case in enumerate(EVAL_CASES):
        print(f"[{i + 1}/{len(EVAL_CASES)}] Running '{case['id']}' as {case['role']}...")
        try:
            result = run_case(case, tokens)
        except Exception as exc:
            result = {
                "id": case["id"], "dimensions": case["dimensions"], "role": case["role"],
                "endpoint": case["endpoint"], "payload": case["payload"],
                "http_status": None, "response": {"error": str(exc)},
                "scores": {}, "overall_pass": False,
            }
        results.append(result)
        status = "PASS" if result["overall_pass"] else ("N/A" if result["overall_pass"] is None else "FAIL")
        print(f"    -> {status}")
        if i < len(EVAL_CASES) - 1:
            time.sleep(PAUSE_BETWEEN_CASES_SECONDS)

    RESULTS_JSON.write_text(json.dumps(results, indent=2, default=str))
    _write_markdown_report(results)

    passed = sum(1 for r in results if r["overall_pass"])
    total_scored = sum(1 for r in results if r["overall_pass"] is not None)
    print(f"\n{passed}/{total_scored} scored cases passed (of {len(results)} total cases).")
    print(f"Results written to {RESULTS_JSON} and {RESULTS_MD}")


def _write_markdown_report(results: list[dict]) -> None:
    lines = [
        "# Eval Results",
        "",
        f"Run against a live stack at `{BASE_URL}`. "
        f"{sum(1 for r in results if r['overall_pass'])}/"
        f"{sum(1 for r in results if r['overall_pass'] is not None)} scored cases passed.",
        "",
        "| Case | Role | Dimensions | Result |",
        "|---|---|---|---|",
    ]
    for r in results:
        status = "✅ PASS" if r["overall_pass"] else ("➖ N/A" if r["overall_pass"] is None else "❌ FAIL")
        lines.append(f"| `{r['id']}` | {r['role']} | {', '.join(r['dimensions'])} | {status} |")

    lines.append("\n## Case Detail\n")
    for r in results:
        lines.append(f"### `{r['id']}`")
        lines.append(f"- **Role:** {r['role']}  **Endpoint:** `{r['endpoint']}`")
        lines.append(f"- **Request:** `{json.dumps(r['payload'])}`")
        lines.append(f"- **HTTP status:** {r['http_status']}")
        for dim, score in r["scores"].items():
            if score is not None:
                lines.append(f"- **{dim}:** {'PASS' if score['pass'] else 'FAIL'} — `{json.dumps(score, default=str)}`")
        reply = r["response"].get("reply") or r["response"].get("executive_summary") or json.dumps(r["response"])
        lines.append(f"- **Response excerpt:** {str(reply)[:500]}")
        if "next_action_reasonableness" in r["dimensions"]:
            lines.append(
                "- **⚠ Human review needed (next-action reasonableness is not "
                "mechanically scored):** read the response excerpt above and "
                "judge whether the recommended action is concrete, specific "
                "to the actual issue, and something a real operator could "
                "act on immediately."
            )
        lines.append("")

    RESULTS_MD.write_text("\n".join(lines))


if __name__ == "__main__":
    main()

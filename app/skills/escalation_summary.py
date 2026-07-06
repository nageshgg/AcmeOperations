"""Customer Escalation Summary Skill.

A "Skill" (per the brief) is a reusable, structured, repeatable workflow --
distinct from a one-off prompt. This module is that workflow: given a
customer name, it gathers input (profile + open issues + full update
history per issue) via the same MCP tools the agent uses, makes exactly
one constrained Gemini call, and returns a validated structured result
(executive summary, risk level, recommended next action, missing
information) -- never free text, and never a shape other than the one
this skill promises its callers.

"""

import asyncio
import json
import os

from google import genai
from langsmith import traceable

import mcp_client

# See app/agent.py for why the Gemini API's own failures are caught as a
# broad `Exception` here rather than the public `google.genai.errors.APIError`:
# empirically, the Interactions API surface raises an internal exception
# (`_gaos.lib.compat_errors.RateLimitError`) that is NOT a subclass of that
# public class, so catching it specifically silently misses real failures.

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


VALID_RISK_LEVELS = {"Low", "Medium", "High", "Critical"}
_REQUIRED_KEY_TYPES: dict[str, type] = {
    "executive_summary": str,
    "risk_level": str,
    "recommended_next_action": str,
    "missing_information": list,
}

SYSTEM_INSTRUCTION = (
    "You generate structured customer escalation summaries for internal "
    "Acme Operations staff. You will be given a customer's profile and "
    "their open issues, each with full update history. Respond with ONLY a "
    "single JSON object (no prose, no markdown fences) with EXACTLY these "
    "keys:\n"
    '  "executive_summary": a concise (3-5 sentence) executive summary of '
    "the customer's overall situation and risk\n"
    '  "risk_level": exactly one of "Low", "Medium", "High", or "Critical"\n'
    '  "recommended_next_action": a single concrete, actionable next step\n'
    '  "missing_information": a JSON array of strings describing any '
    "information that would materially improve this assessment but isn't "
    "available in the provided data (empty array if nothing is missing)\n"
    "Base the risk level on factors such as issue severity/priority, how "
    "long issues have been open, whether root causes and ETAs are known, "
    "and any signals of customer frustration in the update history."
)


@traceable(name="mcp_call_tool", run_type="tool")
async def _call_tool(tool_name: str, arguments: dict, caller: dict) -> dict:
    """Traced wrapper around mcp_client.call_tool so each of this Skill's
    tool calls gets its own LangSmith span nested under
    generate_escalation_summary, mirroring agent.py's _execute_tool --
    minus the RBAC gate, since this Skill only ever calls the 3 read-only
    tools every role may already use, so there's nothing to gate here.
    """
    return await mcp_client.call_tool(tool_name, arguments, caller)


def _validate(parsed: object) -> list[str]:
    """Returns a list of validation problems (empty if `parsed` conforms).
    Kept separate from the calling code so the retry loop below can call it
    twice cleanly, and so this contract is independently testable.
    """
    if not isinstance(parsed, dict):
        return ["response is not a JSON object"]
    problems = []
    for key, expected_type in _REQUIRED_KEY_TYPES.items():
        if key not in parsed:
            problems.append(f"missing required key '{key}'")
        elif not isinstance(parsed[key], expected_type):
            problems.append(f"key '{key}' should be {expected_type.__name__}")
    if "risk_level" in parsed and parsed["risk_level"] not in VALID_RISK_LEVELS:
        problems.append(
            f"risk_level '{parsed.get('risk_level')}' is not one of {sorted(VALID_RISK_LEVELS)}"
        )
    return problems


@traceable(name="gemini_interactions_create", run_type="llm")
async def _create_interaction(**kwargs) -> object:
    """Thin traced wrapper around the blocking Gemini call -- gives each
    Gemini round trip its own LangSmith span, same pattern as
    agent.py's _create_interaction.
    """
    return await asyncio.to_thread(_get_client().interactions.create, **kwargs)


@traceable(name="generate", run_type="chain")
async def _generate(prompt: str) -> dict:
    """One constrained Gemini call, with a single corrective retry if the
    output doesn't validate -- rather than silently returning (or crashing
    on) a malformed result.
    """
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    last_error = "no attempt made"
    for attempt in range(2):
        input_text = prompt
        if attempt == 1:
            input_text += (
                f"\n\nYour previous response did not match the required "
                f"format ({last_error}). Respond again with ONLY the "
                f"corrected JSON object."
            )
        interaction = await _create_interaction(
            model=model,
            system_instruction=SYSTEM_INSTRUCTION,
            input=input_text,
            response_format={"type": "text", "mime_type": "application/json"},
        )
        text = next(
            (
                block.text
                for step in interaction.steps
                if step.type == "model_output" and step.content
                for block in step.content
                if getattr(block, "type", None) == "text"
            ),
            None,
        )
        if text is None:
            last_error = "model produced no text output"
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            last_error = f"invalid JSON ({exc})"
            continue
        problems = _validate(parsed)
        if not problems:
            return parsed
        last_error = "; ".join(problems)

    raise ValueError(
        f"Escalation summary did not conform to the required schema after retry: {last_error}"
    )


@traceable(name="generate_escalation_summary", run_type="chain")
async def generate_escalation_summary(customer_name: str, caller: dict) -> dict:
    """Runs the Customer Escalation Summary Skill for a given customer.

    Gathers input by composing the same MCP tools the agent uses (profile
    + open issues + full history per issue), then makes exactly one
    constrained-output Gemini call. This is a fixed workflow, not an
    open-ended conversation -- there's no tool-calling loop here, because
    the skill already knows exactly what data it needs and in what order,
    which is what makes it a repeatable workflow rather than a one-off
    prompt.
    """
    profile = await _call_tool(
        "get_customer_profile", {"customer_name": customer_name}, caller
    )
    if profile.get("not_found"):
        return {"error": f"No customer found matching '{customer_name}'"}
    if profile.get("multiple_matches"):
        return {
            "error": (
                f"Ambiguous customer name '{customer_name}'; "
                f"matches: {profile['multiple_matches']}"
            )
        }
    if "error" in profile:
        return profile

    open_issues_result = await _call_tool(
        "get_open_issues_for_customer", {"customer_name": customer_name}, caller
    )
    if "error" in open_issues_result:
        return open_issues_result

    issues = open_issues_result.get("issues", [])
    histories = [
        await _call_tool("summarize_issue_history", {"issue_id": issue["id"]}, caller)
        for issue in issues
    ]

    prompt = (
        f"Customer profile:\n{json.dumps(profile, indent=2)}\n\n"
        f"Open issues and their full update history:\n{json.dumps(histories, indent=2)}\n\n"
        "Generate the escalation summary now."
    )

    try:
        result = await _generate(prompt)
    except Exception as exc:  # covers both our own ValueError and any Gemini API failure
        return {"error": str(exc)}

    result["customer_name"] = profile.get("name", customer_name)
    result["open_issue_count"] = len(issues)
    return result

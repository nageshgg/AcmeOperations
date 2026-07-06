"""The agent loop: Gemini's Interactions API driving tools served over MCP.

This is what satisfies "an LLM agent that dynamically reasons about which
tools to call" -- Gemini decides which tool to invoke, in what order, and
how many times, based on the user's message and each tool's result; we
only execute what it asks for (subject to RBAC) and feed results back until
it produces a final answer. Nothing here hardcodes a fixed sequence of tool
calls, and nothing here hardcodes the tools' schemas either -- those are
discovered from mcp_client.get_tool_declarations() at the start of each run
(Step 5: the agent consumes tools via MCP, it doesn't implement them).
"""

import asyncio
import logging
import os
import time

from google import genai

import mcp_client
import observability
import rbac_policy

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Lazily constructed, reused across requests within this process."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


SYSTEM_INSTRUCTION = (
    "You are Acme Operations' internal assistant for sales, support, and "
    "operations staff. Answer questions about customers and their issues "
    "using the available tools -- never guess or fabricate data that a "
    "tool could retrieve. If a tool call is denied because of the user's "
    "role, tell them plainly which role is required rather than implying "
    "the action succeeded."
)

# Hard ceiling on tool-calling rounds so a confused model can't loop forever
# against a live API (and run up cost) on a single user request.
MAX_TOOL_ITERATIONS = 8


async def _execute_tool(tool_name: str, arguments: dict, caller: dict) -> tuple[dict, float]:
    """RBAC-gated tool dispatch -- the single point every tool call passes
    through. The model only ever sees the result of this function; it has
    no path to bypass the role check, and no path to reach mcp_client
    without going through it first. Every call is logged (name, arguments,
    caller, outcome, latency) -- this is the "tool call logs" half of
    Step 8's observability requirement.

    Returns `(result, duration_ms)`. The duration is surfaced to the caller
    (in addition to being logged) so the frontend's "Agent activity" panel
    can display per-tool latency -- a denied call (RBAC) or one that raised
    before `mcp_client.call_tool` returns 0.0 since no real call was timed.
    """
    username = caller.get("preferred_username")
    denial = rbac_policy.check_access(tool_name, caller)
    if denial is not None:
        observability.log_event(
            "tool_call_denied", tool=tool_name, arguments=arguments,
            caller=username, reason=denial,
        )
        return {"error": denial}, 0.0

    start = time.monotonic()
    try:
        result = await mcp_client.call_tool(tool_name, arguments, caller)
    except Exception as exc:  # a single bad tool call shouldn't crash the agent loop
        observability.log_event(
            "tool_call_error", level=logging.ERROR, tool=tool_name,
            arguments=arguments, caller=username, error=str(exc),
        )
        return {"error": f"Tool '{tool_name}' failed: {exc}"}, 0.0

    duration_ms = round((time.monotonic() - start) * 1000, 1)
    observability.log_event(
        "tool_call", tool=tool_name, arguments=arguments, caller=username,
        duration_ms=duration_ms, success="error" not in result,
    )
    return result, duration_ms


async def run_agent(
    user_message: str, caller: dict, previous_interaction_id: str | None = None
) -> dict:
    """Runs the agent loop for one user message and returns the final text
    reply plus a trace of every tool call made (name, arguments, result) --
    the trace is what Step 8's observability logging and eval scoring will
    read, so it's returned structured rather than just logged.

    `previous_interaction_id` (Step 7) continues an existing conversation
    -- Gemini's Interactions API retrieves that conversation's history
    server-side, so this module never needs to resend prior turns itself.
    Pass `None` (the default) to start a fresh conversation; `main.py`
    supplies this from `session_store` (Redis) keyed by the caller's
    conversation_id.

    If the Gemini API itself fails partway through (rate limit, transient
    5xx, etc.), this degrades gracefully rather than raising: any tool
    calls already made (and any writes they performed, e.g. a next_action
    already inserted) are real and already happened, so the response
    surfaces them plus a clear error message instead of a bare 500 that
    hides that a database write may have already succeeded.
    """
    client = _get_client()
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    tool_declarations = await mcp_client.get_tool_declarations()

    run_start = time.monotonic()
    tool_call_log: list[dict] = []
    try:
        interaction = await asyncio.to_thread(
            client.interactions.create,
            model=model,
            input=user_message,
            tools=tool_declarations,
            system_instruction=SYSTEM_INSTRUCTION,
            previous_interaction_id=previous_interaction_id,
        )

        for _ in range(MAX_TOOL_ITERATIONS):
            function_calls = [s for s in interaction.steps if s.type == "function_call"]
            if not function_calls:
                break

            result_steps = []
            for call in function_calls:
                result, duration_ms = await _execute_tool(call.name, call.arguments, caller)
                tool_call_log.append(
                    {
                        "tool": call.name,
                        "arguments": call.arguments,
                        "result": result,
                        "duration_ms": duration_ms,
                    }
                )
                result_steps.append(
                    {
                        "type": "function_result",
                        "call_id": call.id,
                        "name": call.name,
                        "result": result,
                    }
                )

            interaction = await asyncio.to_thread(
                client.interactions.create,
                model=model,
                input=result_steps,
                tools=tool_declarations,
                previous_interaction_id=interaction.id,
            )
    except Exception as exc:
        observability.log_event(
            "agent_run_error", level=logging.ERROR,
            duration_ms=round((time.monotonic() - run_start) * 1000, 1),
            tool_call_count=len(tool_call_log), error=str(exc),
        )
        return {
            "reply": (
                "Sorry, the AI provider returned an error before I could "
                "finish responding. "
                + (
                    f"{len(tool_call_log)} tool call(s) already completed "
                    "(including any data changes) before this happened."
                    if tool_call_log
                    else "No tool calls had been made yet."
                )
            ),
            "tool_calls": tool_call_log,
            "error": str(exc),
        }

    reply_parts = [
        block.text
        for step in interaction.steps
        if step.type == "model_output" and step.content
        for block in step.content
        if getattr(block, "type", None) == "text"
    ]

    observability.log_event(
        "agent_run_complete",
        duration_ms=round((time.monotonic() - run_start) * 1000, 1),
        tool_call_count=len(tool_call_log),
        interaction_id=interaction.id,
    )

    return {
        "reply": "\n".join(reply_parts) if reply_parts else "(no response generated)",
        "tool_calls": tool_call_log,
        "interaction_id": interaction.id,
    }

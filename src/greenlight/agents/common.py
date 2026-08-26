"""Shared agent configuration and the desk factory."""

from __future__ import annotations

import json

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.models.google_llm import Gemini
from google.genai import types

from greenlight.tools import DESK_TOOLS
from greenlight.tools.toolbelt import RunAbortError

# New GCP projects carry tight per-minute Gemini quotas; a 429 mid-loop must not
# kill a run that has live research in session state. The retry MUST live at the
# genai HTTP layer (Gemini.retry_options): ADK converts a surfaced 429 into
# _ResourceExhaustedError immediately, and LlmAgent silently IGNORES an
# unknown retry_config kwarg — the old "8 attempts / 120s" ladder never ran,
# which is how one quota spike aborted a whole paid run (2026-08-26).
_RETRY_HTTP = types.HttpRetryOptions(
    attempts=8, initial_delay=10, max_delay=120, exp_base=2, jitter=0.5
)


def _flash() -> Gemini:
    return Gemini(model="gemini-2.5-flash", retry_options=_RETRY_HTTP)


def _pro() -> Gemini:
    return Gemini(model="gemini-2.5-pro", retry_options=_RETRY_HTTP)


FLASH = _flash()
PRO = _pro()

# Desks are research clerks, not novelists. Low temperature narrows run-to-run
# variance in worklist coverage — the eval harness measures exactly that.
GEN_CONFIG = types.GenerateContentConfig(temperature=0.0)


def tool_error_shield(tool, args, tool_context, error):
    """One hallucinated tool name must not kill a 43-minute paid run.

    ADK raises on unknown tools and on tool exceptions unless this callback
    returns a response; the model then sees the error and self-corrects (the
    'run_code' outage, 2026-08-26). RunAbortError passes through — that one is ours,
    and it means the run SHOULD die."""
    if isinstance(error, RunAbortError) or isinstance(error.__cause__, RunAbortError):
        return None
    return {
        "error": f"{type(error).__name__}: {str(error)[:200]}",
        "guidance": (
            "That tool call failed. Only the tools in your declaration exist — "
            "there is no code execution. Continue with the listed tools; if the "
            "call was malformed, correct the arguments and retry it."
        ),
    }


# History pruning: a 420-entity script drove the clearance desk's conversation
# past the point where single Flash calls took 9 minutes (p99 537s, measured
# 2026-08-26) — prefill scales with input, and every research result ever
# retrieved was riding along on every turn. Keep the recent exchanges verbatim;
# collapse older bulky tool payloads to a stub. Filed flags, budgets, and the
# provenance registry live OUTSIDE the conversation, so nothing auditable is
# lost — and a re-asked research question is a free cache hit.
_KEEP_RECENT_TOOL_RESULTS = 8
_PRUNE_OVER_CHARS = 600
_PRUNE_STUB = {
    "result": (
        "[pruned: this result was already used earlier in the session. If you "
        "genuinely need it again, call the tool again — repeated identical "
        "research questions are answered from cache at no budget cost.]"
    )
}


def prune_stale_tool_results(callback_context, llm_request):
    """before_model_callback: bound per-turn input size on long desk loops."""
    contents = llm_request.contents or []
    resp_idx = [
        i
        for i, c in enumerate(contents)
        if any(getattr(part, "function_response", None) for part in (c.parts or []))
    ]
    if len(resp_idx) <= _KEEP_RECENT_TOOL_RESULTS:
        return None
    for i in resp_idx[:-_KEEP_RECENT_TOOL_RESULTS]:
        pruned = contents[i].model_copy(deep=True)  # never mutate session history
        changed = False
        for part in pruned.parts or []:
            fr = getattr(part, "function_response", None)
            if fr is None or fr.response is None:
                continue
            if len(str(fr.response)) > _PRUNE_OVER_CHARS:
                fr.response = dict(_PRUNE_STUB)
                changed = True
        if changed:
            contents[i] = pruned
    return None


COVERAGE_RULE = """

COVERAGE ROLL-CALL — the contract for finishing. Immediately before calling done(), write out
every item on your worklist with its disposition, one line each:
  <worklist item> -> FLAGGED <flag_id> | CLEARED (one-line reason) | OPEN QUESTION (noted)
An item with no disposition is unfinished work: deal with it before you close. If the budget
is spent, its disposition is an open question, never silence.
"""


def make_desk(name: str, description: str, instruction: str, max_iterations: int) -> LoopAgent:
    """One gatekeeper desk: a LoopAgent over an LlmAgent with the shared toolbelt.

    Desks differ only in instruction and iteration ceiling — the toolbelt is
    identical by design (see docs/TECH_SPEC.md). The inner agent's name must be
    the desk enum value: tools derive the desk identity from it.
    """

    def _instruction(ctx) -> str:
        """Per-turn instruction with a per-desk triage slice. Re-sending all four
        desks' worklists to every desk on every turn multiplied token traffic by
        roughly 4x and was the main driver of 429s on feature-length scripts —
        each desk now carries the shared entity table plus ONLY its own worklist."""
        tri = ctx.state.get("triage") or {}
        if hasattr(tri, "model_dump"):
            tri = tri.model_dump()
        sliced = {"entities": tri.get("entities", []), name: tri.get(name, [])}
        text = instruction + COVERAGE_RULE
        text = text.replace("{triage}", json.dumps(sliced, ensure_ascii=False))
        text = text.replace("{scene_index}", str(ctx.state.get("scene_index", "")))
        return text

    worker = LlmAgent(
        name=name,
        model=FLASH,
        description=description,
        instruction=_instruction,
        tools=list(DESK_TOOLS),
        generate_content_config=GEN_CONFIG,
        on_tool_error_callback=tool_error_shield,
        before_model_callback=prune_stale_tool_results,
    )
    return LoopAgent(
        name=f"{name}_desk",
        description=f"{description} Exits via done() or iteration cap.",
        sub_agents=[worker],
        max_iterations=max_iterations,
    )

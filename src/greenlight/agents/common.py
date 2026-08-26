"""Shared agent configuration and the desk factory."""

from __future__ import annotations

import json
from typing import Any

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
# History pruning, disposition-aware. The desk works case files: research an
# entity, file (or open-question) it, move on. Once an entity has a FILED flag,
# its research payloads are dead weight — verifiers read evidence from session
# state and the provenance registry, never from this conversation. So: archive
# closed case files, never touch open ones. Measured motivation: a 420-entity
# run drove per-call p99 to 537s (prefill scales with input) and pushed the
# model into long-context failure. A first age-based cut (keep last 8) pruned
# results the desk had not yet filed FROM and it forgot paid-for work — the
# graded eval caught it. Disposition is the signal age cannot see.
_PRUNE_RECENCY_FLOOR = 12  # newest exchanges are untouchable: turns in flight
_PRUNE_HARD_CEILING = 40  # beyond this, dispositioned/entity-less results trim
_PRUNE_ABSOLUTE_CEILING = 120  # beyond this, even open-entity results trim
_PRUNE_OVER_CHARS = 2000  # small payloads (file confirmations, briefs) always survive
_PRUNE_NOTE = (
    " …[trimmed: already used. Re-call the tool if you need the full result — "
    "identical research questions are answered from cache at no budget cost.]"
)


def _map_responses_to_entities(contents) -> dict[tuple[int, int], Any]:
    """(content_idx, part_idx) of each function_response -> entity_id of its call.

    Calls precede responses; matched by tool name, first-in-first-out."""
    pending: list[tuple[str, Any]] = []
    out: dict[tuple[int, int], Any] = {}
    for ci, c in enumerate(contents):
        for pi, part in enumerate(c.parts or []):
            fc = getattr(part, "function_call", None)
            if fc is not None:
                args = fc.args if isinstance(fc.args, dict) else {}
                pending.append((fc.name or "", args.get("entity_id")))
            fr = getattr(part, "function_response", None)
            if fr is not None:
                ent = None
                for qi, (nm, e) in enumerate(pending):
                    if nm == (fr.name or ""):
                        ent = e
                        pending.pop(qi)
                        break
                out[(ci, pi)] = ent
    return out


def prune_stale_tool_results(callback_context, llm_request):
    """before_model_callback: bound per-turn input on long desk loops.

    Trims the bulk (keeping a 300-char head) of tool responses whose entity this
    desk has already dispositioned with a filed flag, plus — as a hard ceiling —
    anything older than _PRUNE_HARD_CEILING exchanges. Operates on copies;
    session history and the run journal are never mutated.
    """
    contents = llm_request.contents or []
    resp_idx = [
        i
        for i, c in enumerate(contents)
        if any(getattr(part, "function_response", None) for part in (c.parts or []))
    ]
    if len(resp_idx) <= _PRUNE_RECENCY_FLOOR:
        return None

    desk = getattr(callback_context, "agent_name", "") or ""
    try:
        filed = callback_context.state.get(f"flags:{desk}") or []
    except Exception:
        filed = []
    done_entities = {
        f.get("entity_id") for f in filed if isinstance(f, dict) and f.get("entity_id")
    }

    resp_entity = _map_responses_to_entities(contents)

    protected = set(resp_idx[-_PRUNE_RECENCY_FLOOR:])
    over = len(resp_idx) - _PRUNE_HARD_CEILING
    ceiling_zone = set(resp_idx[:over]) if over > 0 else set()
    over_abs = len(resp_idx) - _PRUNE_ABSOLUTE_CEILING
    absolute_zone = set(resp_idx[:over_abs]) if over_abs > 0 else set()
    for ci in resp_idx:
        if ci in protected:
            continue
        pruned = None
        for pi, part in enumerate(contents[ci].parts or []):
            fr = getattr(part, "function_response", None)
            if fr is None or fr.response is None:
                continue
            raw = str(fr.response)
            if len(raw) <= _PRUNE_OVER_CHARS:
                continue
            ent = resp_entity.get((ci, pi))
            # An un-filed entity's research is working memory: the 40-exchange
            # ceiling caught a PASS-1 result the desk had deferred filing (the
            # Nighthawks miss, eval run 145721). Open items now survive to the
            # absolute bound; the 40 ceiling trims only closed/entity-less work.
            dispositioned = ent is not None and ent in done_entities
            open_item = ent is not None and not dispositioned
            trim = dispositioned or (ci in ceiling_zone and not open_item) or ci in absolute_zone
            if trim:
                if pruned is None:
                    pruned = contents[ci].model_copy(deep=True)
                pruned.parts[pi].function_response.response = {"result": raw[:300] + _PRUNE_NOTE}
        if pruned is not None:
            contents[ci] = pruned
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

"""Shared agent configuration and the desk factory."""

from __future__ import annotations

import json

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.models.google_llm import Gemini
from google.genai import types

from greenlight.tools import DESK_TOOLS

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
    )
    return LoopAgent(
        name=f"{name}_desk",
        description=f"{description} Exits via done() or iteration cap.",
        sub_agents=[worker],
        max_iterations=max_iterations,
    )

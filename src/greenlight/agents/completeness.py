"""Completeness gate: the pipeline does not reach verification while any
extracted entity lacks a disposition.

LoopAgent(check -> sweeper), up to _MAX_ROUNDS rounds. The check is
deterministic Python: it recomputes the unexamined set and escalates (ending
the loop) when it is empty; otherwise it writes the sweep worklist and the
sweeper — a clearance-family desk with the shared toolbelt, scoped to exactly
those items — dispositions them. The sweeper's done() deliberately does not
escalate (escalation would end this loop after one round); the check alone
controls the loop. Anything that survives every round is disclosed as
NOT EXAMINED by the record accounting — never rendered as clean."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent, LoopAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from greenlight.agents.common import make_desk
from greenlight.tools.toolbelt import unexamined_entities

_MAX_ROUNDS = 3
_NAME_CAP = 8

_SWEEP_INSTRUCTION = """You are the clearance department's COMPLETENESS SWEEP.
The four desks have finished, but the items on your worklist below were
extracted from the screenplay and dispositioned by NOBODY. Your one job:
give every item exactly one disposition —

- file_flag if it carries real exposure (with citations, as always);
- record_clearance with a specific reason if it does not (most background
  set-dressing lands here — one honest sentence each);
- note_open_question only for genuine unknowns.

Work every item on the list; call done() when none remain. Do not research
what a competent reader can clear from the script context alone — your
budget is small by design.

ENTITY TABLE AND YOUR WORKLIST:
{triage}

SCENES:
{scene_index}
"""


class _CompletenessCheck(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        missing = unexamined_entities(state)
        if not missing:
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                actions=EventActions(escalate=True),
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text="Completeness gate: every extracted entity has a "
                            "disposition — proceeding to verification."
                        )
                    ],
                ),
            )
            return
        state["sweep_worklist"] = [
            {
                "entity_id": m["entity_id"],
                "surface": m["surface"],
                "scene_ids": m["scene_ids"],
                "note": (
                    f"Left undispositioned by: {', '.join(m.get('desks') or ['(unassigned)'])}. "
                    "Answer THAT desk's question — a rights item (artwork, music, brand, "
                    "person, clip) gets the clearance treatment with research and citations "
                    "if exposure exists; never clear a FEATURED or PLOT_CRITICAL item on "
                    "vibes. Flag it, clear it with a reason, or note the open question — "
                    "silence is not an option."
                ),
            }
            for m in missing
        ]
        named = ", ".join(f"'{m['surface'][:30]}'" for m in missing[:_NAME_CAP])
        more = f" (+{len(missing) - _NAME_CAP} more)" if len(missing) > _NAME_CAP else ""
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        text=f"Completeness gate: {len(missing)} extracted entities have no "
                        f"disposition — sweep round begins: {named}{more}"
                    )
                ],
            ),
        )


agent = LoopAgent(
    name="completeness_gate",
    description="Refuses to advance to verification while extracted entities lack dispositions.",
    max_iterations=_MAX_ROUNDS,
    sub_agents=[
        _CompletenessCheck(
            name="completeness_check",
            description="Deterministic: recomputes the unexamined set each round.",
        ),
        make_desk(
            name="clearance_counsel__sweep",
            description="Dispositions the entities every desk left untouched.",
            instruction=_SWEEP_INSTRUCTION,
            max_iterations=6,
            worklist_state_key="sweep_worklist",
        ),
    ],
)

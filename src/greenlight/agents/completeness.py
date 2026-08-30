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
from greenlight.tools.toolbelt import collapsed_desks, unexamined_entities

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

Work every item on the list; call done() when none remain. When an item
shows a work_item_id, pass it to your disposition tool — that is the only
way scene-level items count. Do not research
what a competent reader can clear from the script context alone — your
budget is small by design.

EXCEPTION — NAMED COMMERCIAL VENUES AND BUSINESSES: these are never cleared
from script context alone. A real venue's exposure turns on its CURRENT
operating status (open, closed, rebranded, who holds the mark now), which is
not on the page. If your budget does not stretch to that research, file
note_open_question naming exactly what must be verified — a one-line
clearance here erases the venue-currency analysis the report is sold on
(run 6 swept four nightclubs clear in a line each and destroyed run 5's
best research).

ENTITY TABLE AND YOUR WORKLIST:
{triage}

SCENES:
{scene_index}
"""


class _CompletenessCheck(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        missing = unexamined_entities(state)

        # Collapsed desks (worklist, zero own dispositions — the territory
        # read-everything-file-nothing failure) get THEIR OWN retry before the
        # generalist sweep touches their items: desk-quality analysis first,
        # the sweep as last resort.
        collapsed = collapsed_desks(state)
        tri = state.get("triage") or {}
        if hasattr(tri, "model_dump"):
            tri = tri.model_dump()
        from greenlight.tools.toolbelt import DESKS as _DESKS

        for d in _DESKS:
            if d in collapsed:
                state[f"retry_worklist:{d}"] = list(tri.get(d) or [])
            else:
                state[f"retry_worklist:{d}"] = []
        if collapsed:
            missing = [m for m in missing if not set(m.get("desks") or []) <= set(collapsed)]
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=(
                                "Completeness gate: desk(s) with ZERO own dispositions — "
                                + ", ".join(collapsed)
                                + " — re-running each desk on its own worklist before any sweep."
                            )
                        )
                    ],
                ),
            )

        if not missing and not collapsed:
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
                "work_item_id": m.get("work_item_id"),
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


def _retry_desk(desk_module_instruction: str, desk: str) -> object:
    """A collapse-retry instance of a desk: same instruction as the real desk
    plus a filing-first preamble; runs only when the check assigned it work."""
    preamble = (
        "RETRY — your desk's previous attempt read scenes but FILED NOTHING and "
        "hit its iteration cap. File dispositions FIRST this time: record each "
        "conclusion the moment its evidence arrives; do not re-survey the "
        "script.\n\n"
    )
    return make_desk(
        name=f"{desk}__retry",
        description=f"Collapse retry for {desk}: files what the first attempt read.",
        instruction=preamble + desk_module_instruction,
        max_iterations=6,
        worklist_state_key=f"retry_worklist:{desk}",
    )


from greenlight.agents.clearance_counsel import INSTRUCTION as _CC_INSTRUCTION  # noqa: E402
from greenlight.agents.ratings_board import INSTRUCTION as _RB_INSTRUCTION  # noqa: E402
from greenlight.agents.safety_underwriter import INSTRUCTION as _SU_INSTRUCTION  # noqa: E402
from greenlight.agents.territory_censor import INSTRUCTION as _TC_INSTRUCTION  # noqa: E402

agent = LoopAgent(
    name="completeness_gate",
    description="Refuses to advance to verification while extracted entities lack dispositions.",
    max_iterations=_MAX_ROUNDS,
    sub_agents=[
        _CompletenessCheck(
            name="completeness_check",
            description="Deterministic: recomputes the unexamined set each round.",
        ),
        _retry_desk(_CC_INSTRUCTION, "clearance_counsel"),
        _retry_desk(_RB_INSTRUCTION, "ratings_board"),
        _retry_desk(_SU_INSTRUCTION, "safety_underwriter"),
        _retry_desk(_TC_INSTRUCTION, "territory_censor"),
        make_desk(
            name="clearance_counsel__sweep",
            description="Dispositions the entities every desk left untouched.",
            instruction=_SWEEP_INSTRUCTION,
            max_iterations=6,
            worklist_state_key="sweep_worklist",
        ),
    ],
)

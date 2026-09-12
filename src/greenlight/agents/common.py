"""Shared agent configuration and the desk factory."""

from __future__ import annotations

import json
from datetime import date as _date
from typing import Any

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.models.google_llm import Gemini
from google.genai import types

from greenlight.agents.evidence import PREQUALIFICATION_EVIDENCE
from greenlight.models import FLASH_MODEL, PRO_MODEL
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


# Model generation is a config knob so the eval gates can trial newer Gemini
# releases without a code change. 3.x models serve only from the global
# endpoint (GOOGLE_CLOUD_LOCATION=global, already prod's setting); the flash
# default is gated on the 21-check fixture eval before any change lands.


# A per-request wall: a stalled global-endpoint stream (seen twice: the Clerks
# case hang, the calibration gate hang) becomes a retryable timeout instead of
# an infinite silent wait. CRITICAL: ADK's client_kwargs REPLACES the
# http_options it builds from retry_options (google_llm.py: kwargs.update),
# so timeout and retry_options must travel in the SAME HttpOptions — passing
# them separately silently disables retries (it cost us a gate run to a 429).
_HTTP_OPTIONS = types.HttpOptions(timeout=480_000, retry_options=_RETRY_HTTP)


def _flash() -> Gemini:
    return Gemini(model=FLASH_MODEL, client_kwargs={"http_options": _HTTP_OPTIONS})


def _pro() -> Gemini:
    return Gemini(model=PRO_MODEL, client_kwargs={"http_options": _HTTP_OPTIONS})


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


def _nudge_tool_use(llm_request) -> None:
    """The territory failure mode: the model muses in prose, calls no tools,
    and the LoopAgent silently exhausts its iterations with zero dispositions.
    If the last model turn produced no function call, append a hard reminder —
    prose turns are invisible; only tool calls exist.

    NOT WIRED (deliberately): this is an opt-in candidate for a
    before_model_callback, pending a gated fixture run — it changes what every
    desk sees on a prose turn, so it ships through the eval, not by default. The
    2026-09-01 review found it calling itself (infinite recursion had it ever
    been registered); that is fixed here so wiring it later is a one-line change.
    The stall class it targets is currently held by filing pressure in the desk
    prompts and the desk-retry path in the completeness gate."""
    contents = llm_request.contents or []
    last_model = next((c for c in reversed(contents) if c.role == "model"), None)
    if last_model is None:
        return
    has_call = any(getattr(part, "function_call", None) for part in last_model.parts or [])
    if has_call:
        return
    from google.genai import types as _t

    llm_request.contents = [
        *contents,
        _t.Content(
            role="user",
            parts=[
                _t.Part(
                    text=(
                        "SYSTEM REMINDER: your previous turn contained no tool call, so it "
                        "accomplished nothing — plans and analysis in prose are discarded. "
                        "Act NOW with a tool: read_scene/find_in_script/research to "
                        "investigate, file_flag/record_clearance/note_open_question to "
                        "disposition, or done() if every worklist item is dispositioned."
                    )
                )
            ],
        ),
    ]


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

    from greenlight.tools.toolbelt import _desk_name_of, desk_flags

    agent = getattr(callback_context, "agent_name", "") or ""
    try:
        filed = desk_flags(callback_context.state, _desk_name_of(agent))
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

A CLEARED ITEM IS SILENCE, NOT A FLAG. Never file a flag whose conclusion is that nothing is
wrong or no action is needed, and never one whose finding describes something ABSENT from the
script ("no minor is present", "no live animal appears", "if X were added..."). If the element
is not written, there is nothing to underwrite — move on. Speculative if/then findings are
noise a producer will reject the whole report over. If you are unsure whether an element is
present, find_in_script decides; if genuinely ambiguous, note_open_question — never a flag.
The one NO_ACTION finding that is real: a territory "release without that market" remedy that
states the creative trade-off — it reports a decision the producer must make, not an absence.

COVERAGE ROLL-CALL — the contract for finishing. Your assignment is YOUR WORKLIST and
nothing else: the entity table is shared context for disambiguation, not your list.
Dispositioning another desk's items ("no safety hazard" on a framed painting) burns your
budget, answers a question nobody asked you, and covers nothing — the first validation run
lost real findings this way. Every worklist item shows a work_item_id; pass it to
file_flag / record_clearance / note_open_question — that id is how the closing gate sees
your work, especially for scene-level items with no entity_id.
FILE AS YOU GO: record dispositions in the same turn their evidence arrives — never
save up filings for a final pass; the iteration cap has eaten desks that read
everything first and filed nothing. Every item ON YOUR WORKLIST ends in exactly one of
three dispositions, each recorded through its tool:
  - a real issue      -> file_flag
  - examined, fine    -> record_clearance(entity_id, reasoning) — REQUIRED, not optional.
                         Silence is indistinguishable from "never looked"; the cleared list
                         renders on the report, so this is how your work becomes visible.
  - genuinely unknown -> note_open_question (unresolved items ONLY — never conclusions;
                         a determination like "cleared, no license needed" belongs in
                         record_clearance)
Immediately before calling done(), write the roll-call: every worklist item, one line each,
with its disposition. An item with no disposition is unfinished work. If the budget is spent,
its disposition is an open question, never silence.

Then, before done(), one more line: name the single worklist item you are LEAST confident
about and what evidence would settle it — file that as note_open_question unless you already
hold that evidence. An honest report has at least one genuine unknown.

ONE FINDING PER ENTITY — each named person, brand, work, or location with an issue gets its
OWN finding with its own citations and remedy. Never fold multiple entities into one umbrella
finding, and anchor each finding to the specific scenes where its issue occurs (max 8 — cite
the strongest occurrences, not every mention).

SOURCE AUTHORITY — a MEDIUM+ finding needs at least one authoritative citation: regulator or
government site (uspto.gov, copyright.gov, csatf.org, filmratings.com, bbfc.co.uk, nma.gov.ae),
primary statute, or law-firm analysis. Fan wikis, forums, and general-interest sites are
background: they may add color, never carry the conclusion. Steer research() there with
restrict_to_domains when chasing a legal question.
"""


def make_desk(
    name: str,
    description: str,
    instruction: str,
    max_iterations: int,
    batch: int | None = None,
    worklist_state_key: str | None = None,
) -> LoopAgent:
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
        from greenlight.tools.toolbelt import _desk_name_of, clearance_batch_slices

        tri = ctx.state.get("triage") or {}
        if hasattr(tri, "model_dump"):
            tri = tri.model_dump()
        desk = _desk_name_of(name)
        if batch is not None:
            slices = clearance_batch_slices(ctx.state)
            my_items = slices[batch] if batch < len(slices) else []
            if not my_items:
                return (
                    "Your batch of the clearance worklist is EMPTY — other batch "
                    "agents hold every item. Call done() immediately with reason "
                    "'empty batch'. Do not research anything."
                )
            sliced = {"entities": tri.get("entities", []), desk: my_items}
            batch_note = (
                f"\n\nBATCH NOTE: you are batch {batch + 1} of the clearance "
                f"department — your worklist below is YOUR slice ({len(my_items)} "
                "items) of the full clearance worklist. Other batch agents hold the "
                "rest; never work an item that is not on your slice. Research results "
                "are shared across batches (identical questions are free cache hits)."
            )
        elif worklist_state_key:
            items = ctx.state.get(worklist_state_key) or []
            if not items:
                return (
                    "Your worklist is EMPTY this round — nothing was assigned to "
                    "you. Call done() immediately with reason 'empty worklist'. "
                    "Do not research anything."
                )
            sliced = {"entities": tri.get("entities", []), desk: items}
            batch_note = ""
        else:
            sliced = {"entities": tri.get("entities", []), desk: tri.get(desk, [])}
            batch_note = ""
        text = PREQUALIFICATION_EVIDENCE + "\n" + instruction + batch_note + COVERAGE_RULE
        text = text.replace("{triage}", json.dumps(sliced, ensure_ascii=False))
        text = text.replace("{scene_index}", str(ctx.state.get("scene_index", "")))
        adaptation = str(ctx.state.get("adaptation_context") or "").strip() or (
            "None provided — treat every dramatization of a real person as "
            "unverified against any source material."
        )
        text = text.replace("{adaptation}", adaptation)
        text = text.replace("{form_facts}", str(ctx.state.get("form_facts", "")))
        # ADK skips state injection for CALLABLE instruction providers, so every
        # {placeholder} must be substituted here or it reaches the model as
        # literal braces. The ratings desk read "The production targets
        # {target_rating}." for its whole life and guessed a target, then built
        # a cut list against the guess while the record stored the real one.
        target = str(ctx.state.get("target_rating") or "no fixed target")
        text = text.replace("{target_rating}", target)
        # Public-domain arithmetic rolls with the calendar: US copyright runs 95
        # years from publication, so works published in (this year - 96) or
        # earlier are PD on 1 January of this year. The prompt used to hard-code
        # "In 2026 ... 1930 or earlier", which turns wrong every New Year.
        text = text.replace("{pd_cutoff}", str(_date.today().year - 96))
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

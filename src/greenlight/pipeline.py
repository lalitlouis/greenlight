"""Assemble and run the GREENLIGHT agent graph.

Phase 1 shape: ScriptParser (deterministic, runs before any agent) -> Triage ->
ClearanceCounsel desk. The panel fan-out and remaining desks arrive in Phase 2 —
the graph here must not silently become the final architecture.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging as _logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# OpenTelemetry's context detach fails noisily when ADK spans cross threads
# (appeared with the 2026-08-29 threading additions): ~1,000 swallowed
# tracebacks per run log, zero functional effect. Quiet that one logger;
# real errors surface through the pipeline's own error paths.
_logging.getLogger("opentelemetry.context").setLevel(_logging.CRITICAL)

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"))

from google.adk.agents import ParallelAgent, SequentialAgent  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from greenlight import parser  # noqa: E402
from greenlight import report as report_mod  # noqa: E402
from greenlight.agents import (  # noqa: E402
    adjudicator,
    clearance_counsel,
    ratings_board,
    safety_underwriter,
    territory_censor,
    triage,
    verification,
)
from greenlight.agents.verification import apply_verdicts  # noqa: E402
from greenlight.costing import accumulate_usage as _accumulate_usage  # noqa: E402
from greenlight.costing import usage_cost_usd as _usage_cost_usd  # noqa: E402
from greenlight.tools import toolbelt  # noqa: E402
from greenlight.tools.toolbelt import DESKS, _desk_name_of  # noqa: E402

APP_NAME = "greenlight"
USER_ID = "producer"
DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"

SEV_ORDER = {"BLOCKER": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "FYI": 4}


# Per-desk live research() budgets. Clearance chases ownership chains and gets more;
# ratings leans on query_precedent once the corpus lands.
DEFAULT_BUDGETS = {
    "clearance_counsel": 28,
    "ratings_board": 5,
    "safety_underwriter": 8,
    "territory_censor": 8,
}

# A feature is not a short: fixed budgets silently thin coverage as page count
# grows (the 109-scene scale test starved territory_censor to zero and the
# name-commonality sweep never ran). Budgets scale with length, capped at 2.5x
# so a feature costs at most ~$4-5 of research, still bounded and predictable.
_EVENT_STALL_S = 900  # 15 min: beyond every bounded client's worst retry envelope

_BUDGET_BASELINE_PAGES = 12
_BUDGET_SCALE_CAP = 2.5


def scaled_budgets(page_count: int) -> dict[str, int]:
    scale = min(_BUDGET_SCALE_CAP, max(1.0, page_count / _BUDGET_BASELINE_PAGES))
    return {desk: round(n * scale) for desk, n in DEFAULT_BUDGETS.items()}


_runner_cache: dict[str, InMemoryRunner] = {}


def get_runner() -> InMemoryRunner:
    """One agent tree + runner per process; each run gets its own session.
    ADK agents are single-parent — rebuilding the tree per run re-parents the
    module-level desks and dies on the second run of a process."""
    if "runner" not in _runner_cache:
        _runner_cache["runner"] = InMemoryRunner(agent=build_root_agent(), app_name=APP_NAME)
    return _runner_cache["runner"]


def build_root_agent() -> SequentialAgent:
    panel = ParallelAgent(
        name="gatekeeper_panel",
        description="The four desks, concurrent and independent — as in a real studio.",
        sub_agents=[
            clearance_counsel.agent,
            ratings_board.agent,
            safety_underwriter.agent,
            territory_censor.agent,
        ],
    )
    from greenlight import prepass
    from greenlight.agents import completeness

    return SequentialAgent(
        name="greenlight_pipeline",
        description=(
            "Screenplay clearance: triage -> pre-pass -> gatekeeper panel -> "
            "completeness gate -> verification."
        ),
        sub_agents=[
            triage.agent,
            prepass.build_agent(),
            panel,
            completeness.agent,
            verification.agent,
            adjudicator.agent,
        ],
    )


def adaptation_context(meta: dict[str, Any], provided: str | None) -> str:
    """The 'based on what?' context: user-provided life-rights/source note plus
    anything the title page declares (Source:, or any 'based on...' line).
    Adapted-from-source scenes and pure invention carry very different
    defamation exposure — the clearance desk calibrates on this."""
    parts: list[str] = []
    if provided and provided.strip():
        parts.append(provided.strip())
    for k, v in (meta or {}).items():
        if not isinstance(v, str) or not v.strip():
            continue
        if k.lower() in ("source", "adaptation") or "based on" in v.lower():
            parts.append(v.strip())
    return "\n".join(dict.fromkeys(parts))  # dedupe, keep order


def _form_facts(scenes: list[dict[str, Any]]) -> str:
    """Measured form profile — the dimension content markers can't carry.
    Deterministic, so the ratings capsule is grounded in fact, not vibes."""
    dlg = sum(len(d.get("line", "")) for sc in scenes for d in sc.get("dialogue", []))
    act = sum(len(sc.get("action", "")) for sc in scenes)
    pct = round(100 * dlg / max(1, dlg + act))
    hi, lo = 60, 35  # dialogue-share bands: talky pictures vs action-forward ones
    register = "dialogue-driven" if pct >= hi else "action-forward" if pct <= lo else "balanced"
    ints = sum(1 for sc in scenes if "INT" in (sc.get("int_ext") or "").upper())
    nights = sum(1 for sc in scenes if "NIGHT" in (sc.get("time_of_day") or "").upper())
    return (
        f"{len(scenes)} scenes; {pct}% of the text is dialogue ({register}); "
        f"{ints} INT / {len(scenes) - ints} EXT; {nights} night scenes"
    )


def _initial_state(
    text: str,
    scenes: list[dict[str, Any]],
    budgets: dict[str, int],
    target_rating: str,
    adaptation: str = "",
    title: str = "",
) -> dict[str, Any]:
    scene_index = "\n".join(f"{s['scene_id']}  p{s['page']:>2}  {s['heading']}" for s in scenes)
    state: dict[str, Any] = {
        "script_text": text,
        "scenes": scenes,
        "script_annotated": parser.annotated_script(text, scenes),
        "scene_index": scene_index,
        "target_rating": target_rating,
        "adaptation_context": adaptation,
        "form_facts": _form_facts(scenes),
        "script_title": title,
    }
    for desk, budget in budgets.items():
        state[f"research_budget:{desk}"] = budget
    return state


def _humanize_result(tool: str, response: Any) -> str:
    """Tool results as sentences, not reprs — the run page reads these aloud."""
    inner = response.get("result", response) if isinstance(response, dict) else response
    if isinstance(inner, str):
        return inner[:180]
    if isinstance(inner, dict):
        if tool == "research":
            if "error" in inner:
                return "Research budget spent — filing from existing sources."
            n = len(inner.get("results", []))
            cached = " (cached)" if inner.get("cached") else ""
            return f"{n} sourced results{cached}"
        if tool == "find_in_script":
            n_scenes = len(inner.get("scenes", []))
            return f"{inner.get('total_matches', 0)} matches across {n_scenes} scenes"
        if tool == "query_precedent":
            comps = inner.get("comparables", [])
            if comps:
                ratings: dict[str, int] = {}
                for c in comps:
                    ratings[c["rating"]] = ratings.get(c["rating"], 0) + 1
                top = max(ratings.items(), key=lambda kv: kv[1])
                return f"{len(comps)} comparables — {top[1]} of them rated {top[0]}"
            return inner.get("error", "no comparables")[:140]
    return str(inner)[:180]


def structured_events(event: Any) -> list[dict[str, Any]]:
    """Typed events for the UI stream. The four desk columns render from these —
    author is the agent name, so desk attribution is free. Clearance batch
    agents (clearance_counsel__bN) are normalized to the base desk so the UI's
    four desk columns stay the contract."""
    out: list[dict[str, Any]] = []
    content = getattr(event, "content", None)
    for part in getattr(content, "parts", None) or []:
        if fc := getattr(part, "function_call", None):
            args = {k: str(v)[:200] for k, v in (fc.args or {}).items() if k != "tool_context"}
            out.append(
                {
                    "type": "tool_call",
                    "agent": _desk_name_of(event.author),
                    "tool": fc.name,
                    "args": args,
                }
            )
        elif fr := getattr(part, "function_response", None):
            out.append(
                {
                    "type": "tool_result",
                    "agent": _desk_name_of(event.author),
                    "tool": fr.name,
                    "brief": _humanize_result(fr.name, fr.response),
                }
            )
        elif (text := getattr(part, "text", None)) and text.strip():
            stripped = text.strip()
            if _desk_name_of(event.author) == "triage" and stripped.startswith("{"):
                # the structured worklist JSON is for the desks, not the viewer
                n = stripped.count('"entity_id"')
                brief = f"{n} entities extracted — worklists out to all four desks"
                out.append({"type": "text", "agent": "triage", "text": brief})
            else:
                out.append(
                    {"type": "text", "agent": _desk_name_of(event.author), "text": stripped[:400]}
                )
    return out


def _describe_event(event: Any) -> list[str]:
    """Terminal progress lines. The desks' tool calls ARE the demo — show them."""
    lines: list[str] = []
    content = getattr(event, "content", None)
    for part in getattr(content, "parts", None) or []:
        if fc := getattr(part, "function_call", None):
            args = fc.args or {}
            brief = ", ".join(
                f"{k}={str(v)[:60]!r}" for k, v in list(args.items())[:3] if k != "tool_context"
            )
            lines.append(
                f"{DIM}[{_desk_name_of(event.author)}]{RESET} -> {BOLD}{fc.name}{RESET}({brief})"
            )
        elif fr := getattr(part, "function_response", None):
            resp = str(fr.response)[:100].replace("\n", " ")
            lines.append(f"{DIM}[{_desk_name_of(event.author)}]    {fr.name} => {resp}{RESET}")
        elif (text := getattr(part, "text", None)) and text.strip():
            lines.append(f"{DIM}[{_desk_name_of(event.author)}]{RESET} {text.strip()[:200]}")
    return lines


async def _salvage_verify(filed, verdicts, state, on_event):
    """A partial report must still be a VERIFIED partial report: when a run aborts
    after desks filed but before verification, run the blinded fan-out directly —
    its per-call backoff usually succeeds once the quota burst has passed."""
    if not filed or verdicts or os.getenv("GREENLIGHT_SKIP_SALVAGE_VERIFY"):
        return verdicts
    try:
        verdicts = await verification.verify_standalone(filed, state)
        if on_event is not None:
            brief = f"Salvage: verified {len(verdicts)} filed flags after the abort."
            on_event({"type": "text", "agent": "verification_panel", "text": brief})
    except Exception:
        pass  # truly unavailable — apply_verdicts fails open with markers
    return verdicts


_UNDERCOVERAGE_FLOOR = 0.5  # mirrors done()'s coverage refusal
_UNDERCOVERAGE_MIN_WORKLIST = 8  # tiny worklists are noise at this ratio


def _incomplete_desks(state: dict[str, Any], verbose: bool) -> list[str]:
    """An empty desk is an error surface, never a clean bill. Two collapse
    classes, both disclosed loudly: a desk with a worklist and ZERO
    dispositions (the territory failure), and a desk that dispositioned
    fewer than half its assigned items (the quieter class the feature-scale
    k=3 caught: dispositions on a truncated slice look like diligence)."""
    incomplete: list[str] = []
    tri = state.get("triage") or {}
    if hasattr(tri, "model_dump"):
        tri = tri.model_dump()
    for d in DESKS:
        worklist = tri.get(d) or []
        n_disp = (
            len(toolbelt.desk_flags(state, d))
            + len(toolbelt.desk_open_questions(state, d))
            + len(toolbelt.desk_cleared(state, d))
        )
        if worklist and n_disp == 0:
            incomplete.append(d)
            if verbose:
                print(f"DESK INCOMPLETE — {d} produced no dispositions for {len(worklist)} items")
        elif len(worklist) >= _UNDERCOVERAGE_MIN_WORKLIST and n_disp < _UNDERCOVERAGE_FLOOR * len(
            worklist
        ):
            incomplete.append(d)
            if verbose:
                print(
                    f"DESK INCOMPLETE — {d} dispositioned {n_disp} of {len(worklist)} "
                    "assigned items (under-coverage)"
                )
    return incomplete


def _desk_coverage(state: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Per-desk instrumentation: what triage assigned vs what got dispositioned.
    On the record so worklist variance is measurable across runs."""
    tri = state.get("triage") or {}
    if hasattr(tri, "model_dump"):
        tri = tri.model_dump()
    out: dict[str, dict[str, int]] = {}
    for d in DESKS:
        items = [it for it in (tri.get(d) or []) if isinstance(it, dict)]
        assigned_ids = {it.get("work_item_id") for it in items if it.get("work_item_id")}
        out[d] = {
            "assigned": len(items),
            "dispositioned": (
                len(toolbelt.desk_flags(state, d))
                + len(toolbelt.desk_open_questions(state, d))
                + len(toolbelt.desk_cleared(state, d))
            ),
            "work_items_assigned": len(assigned_ids),
            "work_items_done": len(assigned_ids & toolbelt.desk_work_items_done(state, d)),
        }
    return out


async def run(  # noqa: PLR0912, PLR0915 - one linear run sequence, deliberately explicit
    script_path: str | Path,
    budgets: dict[str, int] | None = None,
    title_hint: str | None = None,
    on_event: Any = None,
    target_rating: str = "PG-13",
    source_context: str | None = None,
) -> dict[str, Any]:
    """Run the pipeline. on_event, if given, receives each structured event dict
    (see structured_events) as it happens — this is the UI's live stream."""
    source = Path(script_path).read_text()
    meta, scenes = parser.parse_fountain(source)
    # a worker's script file is named by run id — never let that become the title
    title = meta.get("title") or title_hint or Path(script_path).stem
    draft = parser.draft_identity(source, meta, scenes, title)
    verbose = on_event is None  # CLI runs narrate to the console; server runs must
    # keep script-derived text (titles, findings, excerpts) OUT of stdout — stdout
    # is Cloud Logging in production, and the privacy page promises logs are clean.
    if verbose:
        print(f"\n{BOLD}GREENLIGHT{RESET} — {title}: {len(scenes)} scenes parsed\n")

    runner = get_runner()
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        state=_initial_state(
            source,
            scenes,
            budgets or scaled_budgets(scenes[-1]["page"] if scenes else 1),
            target_rating,
            adaptation=adaptation_context(meta, source_context),
            title=title,
        ),
    )

    message = types.Content(
        role="user", parts=[types.Part(text="Run the clearance analysis on the screenplay.")]
    )
    t0 = time.time()
    error: str | None = None
    usage: dict[str, dict[str, int]] = {}
    try:
        # Inactivity watchdog: every client is timeout-bounded (Gemini 480s,
        # Parallel 120s, ClickHouse 60s), yet three multi-hour stalls in one
        # day hung BELOW those bounds (parked streaming reads). If no agent
        # event arrives for _EVENT_STALL_S, the run aborts deliberately and
        # salvages — a bounded, disclosed failure instead of a silent hang.
        agen = runner.run_async(user_id=USER_ID, session_id=session.id, new_message=message)
        it = agen.__aiter__()
        while True:
            try:
                event = await asyncio.wait_for(it.__anext__(), timeout=_EVENT_STALL_S)
            except StopAsyncIteration:
                break
            except TimeoutError:
                with contextlib.suppress(Exception):
                    await agen.aclose()
                raise RuntimeError(
                    f"StallTimeout: no agent event for {_EVENT_STALL_S}s — aborting and salvaging"
                ) from None
            _accumulate_usage(usage, event)
            if on_event is not None:
                for ev in structured_events(event):
                    on_event(ev)
            if verbose:
                for line in _describe_event(event):
                    print(line)
    except Exception as e:
        cause: BaseException = e
        while isinstance(cause, BaseExceptionGroup) and cause.exceptions:
            cause = cause.exceptions[0]  # the group message hides the real failure
        error = f"{type(cause).__name__}: {str(cause)[:300]}"
        print(f"\n{BOLD}RUN ABORTED{RESET} — {type(cause).__name__}\nSalvaging partial results.\n")
        if os.getenv("GREENLIGHT_TRACE"):  # local debugging only: full chain, stderr
            import traceback

            traceback.print_exception(e, file=sys.stderr)

    final = await runner.session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session.id
    )
    state = final.state

    filed = [f for d in DESKS for f in toolbelt.desk_flags(state, d)]
    verdicts = {
        f["flag_id"]: state[f"verdicts:{f['flag_id']}"]
        for f in filed
        if f"verdicts:{f['flag_id']}" in state
    }
    if "verified_flags" in state:
        kept, rejected = state["verified_flags"], state.get("rejected_flags", [])
    else:
        verdicts = await _salvage_verify(filed, verdicts, state, on_event)
        kept, rejected = apply_verdicts(filed, verdicts)
    kept = adjudicator.merge_exact_duplicates(kept)
    adjudication_notes: list[str] = []
    if plan := state.get("adjudication"):
        kept, adjudication_notes = adjudicator.apply_plan(kept, plan)
    kept.sort(key=lambda f: SEV_ORDER.get(f["severity"], 9))

    page_count = scenes[-1]["page"] if scenes else None
    incomplete = _incomplete_desks(state, verbose)
    the_report = report_mod.build_report(
        title,
        kept,
        page_count=page_count,
        rating_prediction=state.get("rating_prediction"),
        incomplete_desks=incomplete,
    )

    with contextlib.suppress(Exception):
        await runner.session_service.delete_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session.id
        )

    # Referential integrity for the cleared section: a desk's clearance note
    # written mid-run may cite a flag id the verifier later rejected ("flagged
    # as BLOCKER under F401") — without this, the report points at findings
    # that no longer exist.
    rejected_ids = {f.get("flag_id") for f in rejected if f.get("flag_id")}
    if rejected_ids:
        pat = re.compile(r"\b(" + "|".join(sorted(rejected_ids)) + r")\b")
        for d in DESKS:
            for entry in toolbelt.desk_cleared(state, d):
                reasoning = entry.get("reasoning") or ""
                if pat.search(reasoning):
                    entry["reasoning"] = pat.sub(
                        r"\1 (later rejected in verification — see Rejected)", reasoning
                    )

    record = {
        "script_title": title,
        "desks_incomplete": incomplete,
        "script_path": str(script_path),
        "draft": draft,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - t0, 1),
        "error": error,
        "research_failures": int(state.get("research_failures", 0)),
        "resource_stats": state.get("resource_stats") or {"attempted": 0, "recovered": 0},
        "scenes": len(scenes),
        "scene_meta": {
            sc["scene_id"]: {
                "heading": sc.get("heading", ""),
                "page": sc.get("page", ""),
                "number": sc.get("number", ""),
            }
            for sc in scenes
        },
        "entities": state.get("triage", {}).get("entities", []),
        "desk_coverage": _desk_coverage(state),
        "unexamined": toolbelt.unexamined_entities(state),
        "flags": kept,
        "rejected_flags": rejected,
        "verdicts": verdicts,
        "report": the_report,
        "adjudication_notes": adjudication_notes,
        "open_questions": {d: toolbelt.desk_open_questions(state, d) for d in DESKS},
        "cleared": {
            **{d: toolbelt.desk_cleared_own(state, d) for d in DESKS},
            **(
                {"completeness_sweep": sweep_cleared}
                if (sweep_cleared := list(state.get("cleared:clearance_counsel__sweep") or []))
                else {}
            ),
        },
        "research_budget_left": {d: toolbelt.desk_budget_left(state, d) for d in DESKS},
        "research": {
            k: v for k, v in state.items() if isinstance(k, str) and k.startswith("research:")
        },
    }
    searches = {
        v.get("search_id")
        for v in record["research"].values()
        if isinstance(v, dict) and v.get("search_id")
    }
    record["gemini_usage"] = usage
    record["cost_usd"] = _usage_cost_usd(usage, len(searches))
    return record


def save_run(record: dict[str, Any], out_dir: Path | None = None) -> Path:
    out_dir = out_dir or (ROOT / "runs")
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"run_{time.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(record, indent=2))
    return path


def print_summary(record: dict[str, Any]) -> None:
    rep = record.get("report", {})
    score = rep.get("greenlight_score")
    print(
        f"\n{BOLD}=== {record['script_title']} — Greenlight Score {score}/100 — "
        f"{len(record['flags'])} flags ({len(record.get('rejected_flags', []))} rejected in "
        f"verification), {len(record['entities'])} entities, {record['elapsed_s']}s ==={RESET}\n"
    )
    if cost := rep.get("est_clearance_cost_usd"):
        print(f"est. clearance cost: ${cost[0]:,.0f}-${cost[1]:,.0f} (rule-of-thumb, not quotes)\n")
    for f in record["flags"]:
        cost = f["remedy"].get("est_cost_usd")
        cost_s = f" ~${cost[0]:,.0f}-${cost[1]:,.0f} (est.)" if cost else ""
        print(
            f"{BOLD}{f['flag_id']} [{f['severity']}] {f['category']}{RESET} "
            f"({', '.join(f['scene_ids'])}){cost_s}"
        )
        print(f"  {f['finding'][:300]}")
        print(f"  remedy: {f['remedy']['action']} — {f['remedy']['detail'][:150]}")
        for c in f["citations"]:
            print(f'  {DIM}cite: {c["url"]} — "{c["excerpt"][:110]}..."{RESET}')
        print()
    for n in record.get("adjudication_notes", []):
        print(f"{DIM}adjudicator: {n[:180]}{RESET}")
    for f in record.get("rejected_flags", []):
        print(
            f"{DIM}rejected in verification: {f['flag_id']} [{f['severity']}] "
            f"{f['category']} — {f['rejection_reason'][:140]}{RESET}"
        )
    for desk, qs in record["open_questions"].items():
        for q in qs:
            print(f"{DIM}open question ({desk}): {q}{RESET}")

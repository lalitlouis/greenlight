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
from greenlight.agents.evidence_review import review_incomplete  # noqa: E402
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
        # apply_verdicts leaves a MISSING verdict untouched — it marks only the
        # per-flag fail_open ones — so a wholesale failure here used to ship
        # entirely unverified flags that render exactly like verified ones.
        # Mark every flag explicitly: the report then withholds its score
        # (verification_degraded) instead of scoring an unverified run.
        verdicts = {
            f["flag_id"]: {
                "verdict": "SUPPORTED",
                "reason": "verification unavailable — salvage path could not reach the verifier",
                "fail_open": True,
            }
            for f in filed
        }
    return verdicts


_UNDERCOVERAGE_FLOOR = 0.5  # mirrors done()'s coverage refusal
_UNDERCOVERAGE_MIN_WORKLIST = 8  # tiny worklists are noise at this ratio


def _collect_guard_manifest(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Union every guard trail: the verification panel's, each desk agent's
    filing-gate rejections (batch agents write under their own suffixed names —
    the per-agent state-key rule), and assembly-stage guards."""
    out = list(state.get("guard_manifest:verification") or [])
    for desk in toolbelt.DESKS:
        for name in toolbelt.batch_agent_names(desk):
            out.extend(state.get(f"guard_manifest:{name}") or [])
    out.extend(state.get("guard_manifest:assembly") or [])
    return out


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
        n_disp = _own_dispositions(state, d)
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


def _own_dispositions(state: dict[str, Any], desk: str) -> int:
    """A desk's OWN dispositions, counted per ENTITY. Mirrors
    toolbelt.collapsed_desks (the gate's retry signature): the completeness
    sweeper's generalist clearances do not count for the desk, and a desk that
    filed three flags on one song dispositioned one item, not three (review
    2026-09-01 B16 — the under-coverage ratio inflated on multi-flag entities)."""
    flags = toolbelt.desk_flags(state, desk)
    cleared = toolbelt.desk_cleared_own(state, desk)
    entities = {f.get("entity_id") for f in flags if f.get("entity_id")} | {
        c.get("entity_id") for c in cleared if isinstance(c, dict) and c.get("entity_id")
    }
    scene_level = sum(1 for f in flags if not f.get("entity_id")) + sum(
        1 for c in cleared if not (isinstance(c, dict) and c.get("entity_id"))
    )
    return len(entities) + scene_level + len(toolbelt.desk_open_questions(state, desk))


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


_FLAG_ID_RE = re.compile(r"\bF\d{3,4}\b")
# entity / work-item / sweep ids are ours, not the producer's: "For E030 (CC-W030,
# Limp Bizkit cue in S032)" and "For SU-W008 (mechanical bull…)" reached a live
# report's open questions (2026-09-02). Scene ids (S###) and finding ids (F####) stay.
_INTERNAL_ID_RE = re.compile(
    r"\b(?:[EP]\d{3}|[A-Z]{2}-W\d{3}|[A-Z]{2}-AX-[A-Z0-9-]+|[A-Z]{2}-CENSUS-[A-Z]+"
    r"|SW-[A-Z]{2}-[EP]\d{3})\b"
)


def _strip_internal_ids(text: str) -> str:
    """Remove internal ids from prose and repair the punctuation they leave behind."""
    if not _INTERNAL_ID_RE.search(text):
        return text
    t = _INTERNAL_ID_RE.sub("", text)
    t = re.sub(r"\(\s*[,;:]?\s*", "(", t)
    t = re.sub(r"\s*[,;:]?\s*\)", ")", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"^\s*(?:For\s+)?\(([^)]*)\)\s*[:,]?\s*", lambda m: m.group(1) + ": ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    return t[:1].upper() + t[1:] if t else t


# an id not yet carrying its "(later rejected …)" / "(withdrawn …)" annotation
_UNANNOTATED_ID_RE = re.compile(r"\b(F\d{3,4})\b(?! \((?:later rejected|withdrawn))")
_UNRESOLVED_TEMPLATE = "Unresolved —"
_MIN_ROUTE_SURFACE = 4  # 'Sam' inside a word must never route a question


def _absorption_map(
    before: list[dict[str, Any]], after: list[dict[str, Any]], plan: dict[str, Any] | None
) -> dict[str, str]:
    """{absorbed flag id -> surviving flag id} across BOTH merge paths. The
    plan names its survivors; code dedupe does not, so an absorbed flag is
    matched to the survivor the same way merge_exact_duplicates would have
    (same desk, same category, same disposition, script-wide or scene
    overlap). Chains resolve to their fixpoint. Review 2026-09-01 B4: 1-8
    flags per run vanished with every cross-reference to them left dangling."""
    after_ids = {f["flag_id"] for f in after}
    planned: dict[str, str] = {}
    for action in (plan or {}).get("merges", []) or []:
        for fid in action.get("merged_flag_ids") or []:
            planned[fid] = str(action.get("surviving_flag_id") or "")
    out: dict[str, str] = {}
    for f in before:
        fid = f["flag_id"]
        if fid in after_ids:
            continue
        survivor = planned.get(fid)
        if survivor not in after_ids:
            survivor = None
            script_wide = str(f.get("category") or "").startswith(("rating_", "territory_"))
            no_action = (f.get("remedy") or {}).get("action") == "NO_ACTION"
            for g in after:
                if g.get("agent") != f.get("agent") or g.get("category") != f.get("category"):
                    continue
                if ((g.get("remedy") or {}).get("action") == "NO_ACTION") != no_action:
                    continue
                if script_wide or set(g.get("scene_ids") or []) & set(f.get("scene_ids") or []):
                    survivor = g["flag_id"]
                    break
        if survivor:
            out[fid] = survivor
    for k in list(out):
        seen, v = {k}, out[k]
        while v in out and v not in seen:
            seen.add(v)
            v = out[v]
        out[k] = v
    return out


def finalize_record_after_verification(record: dict[str, Any]) -> list[dict[str, Any]]:  # noqa: PLR0912, PLR0915 - one integrity pass, deliberately linear
    """The ONE post-verification integrity pass over an assembled record —
    shared by the live pipeline and the reverify endpoint so the two cannot
    drift (review 2026-09-01 A5/B4/B12). Mutates the record; returns guard-
    manifest entries. Deterministic.

    1. Absorbed ids (merge/dedupe) are rewritten to their survivor everywhere
       prose can cite a finding: cleared reasoning, open questions, finding and
       remedy text, adjudication notes.
    2. Rejected ids carry "(later rejected in verification — see Rejected)" and
       marginal-gate withdrawals "(withdrawn — see Open questions)" — in EVERY
       cleared bucket (the sweeper's included), never only the desks'.
    3. Adjudication notes may only name ids that render.
    4. A finding whose prose names a scene the script does not have is
       manifest-recorded (the eval fails it; the filing gate rejects it live).
    5. An open question that names a rendered same-desk finding, or the surface
       of an entity carrying one, is a FOLLOW-UP on that finding, not a second
       item in the unknowns count — routed to record["oq_followups"].
    6. entity_accounting.items_examined: the decomposition behind
       "N items examined", so the header can be reconciled by a reader.
    """
    from greenlight import entity_accounting

    manifest: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = record.get("flags") or []
    rep_flags: list[dict[str, Any]] = (record.get("report") or {}).get("flags") or []
    kept_ids = {f["flag_id"] for f in flags}
    rejected_ids = {
        f.get("flag_id") for f in record.get("rejected_flags") or [] if f.get("flag_id")
    }
    withdrawn = set(record.get("withdrawn_flag_ids") or [])
    raw_absorbed = record.get("absorbed_into") or {}
    # a flag absorbed into a survivor the marginal gate later withdrew is itself
    # withdrawn — its id must annotate, not dangle
    withdrawn |= {k for k, v in raw_absorbed.items() if v in withdrawn}
    absorbed = {k: v for k, v in raw_absorbed.items() if v in kept_ids}
    record["absorbed_into"] = absorbed

    def _rewrite(text: str) -> str:
        if not absorbed:
            return text
        out = _FLAG_ID_RE.sub(lambda m: absorbed.get(m.group(0), m.group(0)), text)
        # "F4003 and F4003" after a rewrite is one reference, not two
        return re.sub(r"\b(F\d{3,4})\b(\s*(?:,|and|&|/)\s*)\1\b", r"\1", out)

    def _annotate(text: str) -> str:
        # the withdrawn-notice template already states the rejection; annotating
        # its id produced "(F1018 (later rejected …), S030…)" on a live report
        if text.startswith(_UNRESOLVED_TEMPLATE):
            return text

        def sub(m: re.Match[str]) -> str:
            fid = m.group(1)
            if fid in kept_ids:
                return fid
            if fid in rejected_ids:
                return f"{fid} (later rejected in verification — see Rejected)"
            if fid in withdrawn:
                return f"{fid} (withdrawn — see Open questions)"
            return fid

        return _UNANNOTATED_ID_RE.sub(sub, text)

    # 1 + 2: cleared (every bucket), findings, remedies
    for _desk, items in (record.get("cleared") or {}).items():
        for c in items or []:
            if isinstance(c, dict) and c.get("reasoning"):
                c["reasoning"] = _strip_internal_ids(_annotate(_rewrite(str(c["reasoning"]))))
    seen_flag_objs: set[int] = set()
    for f in [*flags, *rep_flags]:
        if id(f) in seen_flag_objs:
            continue
        seen_flag_objs.add(id(f))
        if f.get("finding"):
            f["finding"] = _strip_internal_ids(_annotate(_rewrite(str(f["finding"]))))
        rem = f.get("remedy") or {}
        if rem.get("detail"):
            rem["detail"] = _strip_internal_ids(_annotate(_rewrite(str(rem["detail"]))))
    # 3: adjudication notes — rewrite absorbed ids, then drop anything dangling
    notes = [_rewrite(str(n)) for n in record.get("adjudication_notes") or []]
    record["adjudication_notes"] = [n for n in notes if set(_FLAG_ID_RE.findall(n)) <= kept_ids]
    # 4: prose naming a scene the script does not have
    scene_meta = record.get("scene_meta")
    if isinstance(scene_meta, dict) and scene_meta:
        for f in flags:
            body = f"{f.get('finding') or ''} {(f.get('remedy') or {}).get('detail') or ''}"
            missing = sorted(set(re.findall(r"\bS\d{3}\b", body)) - set(scene_meta))
            if missing:
                manifest.append(
                    {
                        "guard": "prose_scene_missing",
                        "stage": "assembly",
                        "flag_id": f["flag_id"],
                        "scene_ids": missing,
                    }
                )
    # 5: open-question routing
    surf_by_id = {
        str(e.get("entity_id") or ""): str(e.get("surface") or "")
        for e in record.get("entities") or []
        if e.get("entity_id")
    }
    fold = (record.get("entity_accounting") or {}).get("fold") or {}
    followups: dict[str, list[str]] = {
        k: [_strip_internal_ids(str(x)) for x in v]
        for k, v in (record.get("oq_followups") or {}).items()
        if k in kept_ids
    }
    new_oq: dict[str, list[Any]] = {}
    for desk, qs in (record.get("open_questions") or {}).items():
        desk_flags = [f for f in flags if f.get("agent") == desk]
        desk_ids = [f["flag_id"] for f in desk_flags]
        keep: list[Any] = []
        for q in qs or []:
            text = _strip_internal_ids(_annotate(_rewrite(str(q))))
            if text.startswith(_UNRESOLVED_TEMPLATE):
                keep.append(text)  # names a rejected/withdrawn id by design
                continue
            target = next((fid for fid in desk_ids if fid in set(_FLAG_ID_RE.findall(text))), None)
            if target is None:
                for f in desk_flags:
                    eid = str(f.get("entity_id") or "")
                    surfaces = {surf_by_id.get(eid, ""), surf_by_id.get(fold.get(eid, eid), "")}
                    for surface in surfaces:
                        if len(surface) >= _MIN_ROUTE_SURFACE and re.search(
                            rf"(?<!\w){re.escape(surface)}(?!\w)", text, re.IGNORECASE
                        ):
                            target = f["flag_id"]
                            break
                    if target:
                        break
            if target:
                followups.setdefault(target, []).append(text)
                manifest.append(
                    {
                        "guard": "open_question_routed",
                        "stage": "assembly",
                        "flag_id": target,
                        "desk": desk,
                        "matched": text[:120],
                    }
                )
            else:
                keep.append(text)
        new_oq[desk] = keep
    record["open_questions"] = new_oq
    record["oq_followups"] = followups
    # 6: the header decomposition
    acct = record.get("entity_accounting")
    if isinstance(acct, dict):
        acct["items_examined"] = entity_accounting.items_examined(record)
    return manifest


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
    # The draft's own claim about itself outranks the uploaded filename: Fountain
    # metadata first, then the structural PDF title page, then the hint (run-13:
    # "The Hangover 2009" was the filename beating the title page's THE HANGOVER).
    title = (
        meta.get("title")
        or parser.detect_structural_title(source)
        or title_hint
        or Path(script_path).stem
    )
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
        # parity with the main panel: a sourcing-failure rejection becomes an
        # open question rather than silently retiring the hazard. (Re-sourcing
        # and the rating reconcile still do NOT run on this path — they need a
        # live client, which is precisely what the abort suggests is missing.)
        for key, entries in verification.demotion_entries(rejected).items():
            state[key] = list(state.get(key) or []) + entries
    # PLAN FIRST, then code dedupe. Reversed, merge_exact_duplicates absorbed
    # flags the model's plan named as survivors — and apply_plan ignores unknown
    # ids — so the whole action no-oped and its merge, category normalization
    # and on-record rationale were lost, on exactly the duplicate-heavy runs the
    # adjudicator exists for. The plan was generated from the PRE-dedupe
    # verified_flags, so it must see that same set.
    adjudication_notes: list[str] = []
    _pre_merge = list(kept)
    plan = state.get("adjudication")
    if plan:
        kept, adjudication_notes = adjudicator.apply_plan(kept, plan)
    kept = adjudicator.merge_exact_duplicates(kept)
    absorbed_into = _absorption_map(_pre_merge, kept, plan)
    # ASSERTION (run-8): no adjudication entry may reference a flag id that does
    # not render. The Pro adjudicator hallucinated F2008/F2003 against its own
    # input, and dedupe can absorb a flag a note already named — either way the
    # report showed a note about a finding nobody could find. Drop those notes.
    _rendered_ids = {f["flag_id"] for f in kept}
    adjudication_notes = [
        n for n in adjudication_notes if set(re.findall(r"\bF\d{3,4}\b", n)) <= _rendered_ids
    ]
    # A finding's prose may not name a scene outside its coordinates (assertion,
    # run-8): F3006 argued about S069 in its body while S069 was not in its
    # scene_ids and rendered its own clean row. Union the valid prose-named
    # scenes in so prose and coordinates agree.
    _valid_sids = {s["scene_id"] for s in scenes}
    for f in kept:
        body = f"{f.get('finding') or ''} {(f.get('remedy') or {}).get('detail') or ''}"
        named = {s for s in re.findall(r"\bS\d{3}\b", body) if s in _valid_sids}
        if named - set(f["scene_ids"]):
            f["scene_ids"] = sorted(set(f["scene_ids"]) | named, key=lambda x: int(x[1:]))
        # Citations accrue past file_flag (verifier re-source, adjudicator merge),
        # so the filing-time dedupe misses www/m./same-page duplicates that then
        # render as two sources and inflate the count. Collapse them once here, at
        # the single choke point every surface (web, PDF, one-sheet) reads from.
        if f.get("citations"):
            f["citations"] = toolbelt._dedupe_cits(f["citations"])
    kept.sort(key=lambda f: SEV_ORDER.get(f["severity"], 9))

    # HARD GATE (run-13 item 3): a rating finding without its measured marginal
    # does not render as a finding — three runs of "the plumbing works but
    # nothing came out" is what a soft check buys. It demotes to the ratings
    # desk's open questions (absence must never render as clean), and the gate
    # firing marks the desk incomplete so the SCORE IS WITHHELD — demotion must
    # never make the hero number go UP.
    _no_marginal = [
        f for f in kept if (f.get("category") or "").startswith("rating_") and not f.get("marginal")
    ]
    _assembly_manifest: list[dict[str, Any]] = []
    if _no_marginal:
        kept = [f for f in kept if f not in _no_marginal]
        oq_key = "open_questions:ratings_board"
        oq = list(state.get(oq_key) or [])
        for f in _no_marginal:
            oq.append(
                f"Unresolved — the {str(f.get('category', '')).replace('_', ' ')} finding "
                f"({f['flag_id']}, {', '.join(f.get('scene_ids') or [])}) was filed without a "
                "measured CARA marginal, so it does not render as a finding. The driver may be "
                "real; rerun with rating_boundary evidence."
            )
            _assembly_manifest.append(
                {
                    "guard": "marginal_hard_gate",
                    "stage": "assembly",
                    "flag_id": f["flag_id"],
                    "outcome": "demoted_to_open_question",
                }
            )
        state[oq_key] = oq
        if state.get("rating_prediction"):
            # the reconcile that trims a rejected finding's clause from the
            # rationale/cut list runs inside the verification panel with a live
            # client; an assembly-stage demotion has none. Say so on the record
            # rather than leave the panel silently resting on a withdrawn driver.
            _assembly_manifest.append(
                {
                    "guard": "marginal_hard_gate",
                    "stage": "assembly",
                    "outcome": "rating_reconcile_not_run",
                    "flag_ids": [f["flag_id"] for f in _no_marginal],
                }
            )
            # the coverage set's inputs, however, recompute deterministically —
            # boundary_eval is pure and needs no client
            from greenlight.agents.verification import _recompute_boundary_after_drop

            _new_pred, _set_note = _recompute_boundary_after_drop(
                state["rating_prediction"], _no_marginal, kept
            )
            if _set_note:
                state["rating_prediction"] = _new_pred
                _assembly_manifest.append(
                    {"guard": "conformal_set_recomputed", "stage": "assembly", **_set_note}
                )
        # gate #15: the dangling-note filter ran BEFORE this gate existed in the
        # sequence — a demoted finding's adjudication note survived it. Re-filter
        # against what actually renders now.
        _rendered_now = {f["flag_id"] for f in kept}
        adjudication_notes = [
            n for n in adjudication_notes if set(re.findall(r"\bF\d{3,4}\b", n)) <= _rendered_now
        ]
    state["guard_manifest:assembly"] = _assembly_manifest

    page_count = parser.printed_page_count(source) or (scenes[-1]["page"] if scenes else None)
    incomplete = _incomplete_desks(state, verbose)
    # Calibration (gate #11 collision): ONE demoted rating finding beside
    # surviving marginal-carrying ones is an ordinary demotion — an honest open
    # question, like any sourcing failure — and must not withhold the score.
    # The inflation danger is the gate GUTTING the desk: demotions that leave
    # ZERO rendered rating findings mark it incomplete and withhold.
    _rating_left = any((f.get("category") or "").startswith("rating_") for f in kept)
    if _no_marginal and not _rating_left and "ratings_board" not in incomplete:
        incomplete.append("ratings_board")
    the_report = report_mod.build_report(
        title,
        kept,
        page_count=page_count,
        rating_prediction=state.get("rating_prediction"),
        incomplete_desks=incomplete,
        verification_incomplete=review_incomplete(verdicts),
    )

    with contextlib.suppress(Exception):
        await runner.session_service.delete_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session.id
        )

    record = {
        "script_title": title,
        "desks_incomplete": incomplete,
        "script_path": str(script_path),
        "draft": draft,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        # Which build produced this record. Cloud Run injects K_REVISION (e.g.
        # greenlight-00185-7q5); local runs record "local". Without it a corpus
        # or code change under the panel cannot be attributed to a deploy.
        "build": os.environ.get("K_REVISION", "local"),
        # Run-13: every guard fire, queryable from the record (internal — the
        # report does not render it). Union of the verification panel's trail,
        # each desk's filing-gate rejections, and assembly-stage guards.
        "guard_manifest": _collect_guard_manifest(state),
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
        # same guard the four other triage readers use: ADK may hand back the
        # pydantic form, and an AttributeError HERE would crash record assembly
        # after the whole paid run had already finished
        "entities": _triage_entities(state),
        "desk_coverage": _desk_coverage(state),
        "unexamined": toolbelt.unexamined_entities(state),
        "flags": kept,
        "rejected_flags": rejected,
        "verdicts": verdicts,
        "report": the_report,
        "adjudication_notes": adjudication_notes,
        "absorbed_into": absorbed_into,
        "withdrawn_flag_ids": [f["flag_id"] for f in _no_marginal],
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
    from greenlight import entity_accounting

    record["entity_accounting"] = entity_accounting.account(record["entities"])
    # run-13 items 1 + 6a: display-only cleared-path transforms — cid strip,
    # body-reference suppression index, receipt-gated work-claim rewrites.
    record["guard_manifest"] = (
        record.get("guard_manifest") or []
    ) + entity_accounting.polish_record(record)
    # the shared post-verification integrity pass (also run by reverify):
    # absorbed-id rewrite, rejected/withdrawn annotation in every bucket,
    # dangling notes, phantom prose scenes, open-question routing, header math
    record["guard_manifest"] = record["guard_manifest"] + finalize_record_after_verification(record)
    return record


def _triage_entities(state: Any) -> list[dict[str, Any]]:
    tri = state.get("triage") or {}
    if hasattr(tri, "model_dump"):
        tri = tri.model_dump()
    return list(tri.get("entities", []) or []) if isinstance(tri, dict) else []


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

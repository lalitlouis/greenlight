"""Assemble and run the GREENLIGHT agent graph.

Phase 1 shape: ScriptParser (deterministic, runs before any agent) -> Triage ->
ClearanceCounsel desk. The panel fan-out and remaining desks arrive in Phase 2 —
the graph here must not silently become the final architecture.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

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
from greenlight.tools.toolbelt import DESKS  # noqa: E402

APP_NAME = "greenlight"
USER_ID = "producer"
DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"

SEV_ORDER = {"BLOCKER": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "FYI": 4}


# Per-desk live research() budgets. Clearance chases ownership chains and gets more;
# ratings leans on query_precedent once the corpus lands.
DEFAULT_BUDGETS = {
    "clearance_counsel": 18,
    "ratings_board": 5,
    "safety_underwriter": 8,
    "territory_censor": 8,
}


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
    return SequentialAgent(
        name="greenlight_pipeline",
        description="Screenplay clearance: triage -> gatekeeper panel -> verification.",
        sub_agents=[triage.agent, panel, verification.agent, adjudicator.agent],
    )


def _initial_state(
    text: str, scenes: list[dict[str, Any]], budgets: dict[str, int]
) -> dict[str, Any]:
    scene_index = "\n".join(f"{s['scene_id']}  p{s['page']:>2}  {s['heading']}" for s in scenes)
    state: dict[str, Any] = {
        "script_text": text,
        "scenes": scenes,
        "script_annotated": parser.annotated_script(text, scenes),
        "scene_index": scene_index,
    }
    for desk, budget in budgets.items():
        state[f"research_budget:{desk}"] = budget
    return state


def structured_events(event: Any) -> list[dict[str, Any]]:
    """Typed events for the UI stream. The four desk columns render from these —
    author is the agent name, so desk attribution is free."""
    out: list[dict[str, Any]] = []
    content = getattr(event, "content", None)
    for part in getattr(content, "parts", None) or []:
        if fc := getattr(part, "function_call", None):
            args = {k: str(v)[:200] for k, v in (fc.args or {}).items() if k != "tool_context"}
            out.append({"type": "tool_call", "agent": event.author, "tool": fc.name, "args": args})
        elif fr := getattr(part, "function_response", None):
            out.append(
                {
                    "type": "tool_result",
                    "agent": event.author,
                    "tool": fr.name,
                    "brief": str(fr.response)[:200],
                }
            )
        elif (text := getattr(part, "text", None)) and text.strip():
            out.append({"type": "text", "agent": event.author, "text": text.strip()[:400]})
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
            lines.append(f"{DIM}[{event.author}]{RESET} -> {BOLD}{fc.name}{RESET}({brief})")
        elif fr := getattr(part, "function_response", None):
            resp = str(fr.response)[:100].replace("\n", " ")
            lines.append(f"{DIM}[{event.author}]    {fr.name} => {resp}{RESET}")
        elif (text := getattr(part, "text", None)) and text.strip():
            lines.append(f"{DIM}[{event.author}]{RESET} {text.strip()[:200]}")
    return lines


async def run(
    script_path: str | Path,
    budgets: dict[str, int] | None = None,
    on_event: Any = None,
) -> dict[str, Any]:
    """Run the pipeline. on_event, if given, receives each structured event dict
    (see structured_events) as it happens — this is the UI's live stream."""
    source = Path(script_path).read_text()
    meta, scenes = parser.parse_fountain(source)
    title = meta.get("title", Path(script_path).stem)
    print(f"\n{BOLD}GREENLIGHT{RESET} — {title}: {len(scenes)} scenes parsed\n")

    runner = InMemoryRunner(agent=build_root_agent(), app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        state=_initial_state(source, scenes, budgets or DEFAULT_BUDGETS),
    )

    message = types.Content(
        role="user", parts=[types.Part(text="Run the clearance analysis on the screenplay.")]
    )
    t0 = time.time()
    error: str | None = None
    try:
        async for event in runner.run_async(
            user_id=USER_ID, session_id=session.id, new_message=message
        ):
            if on_event is not None:
                for ev in structured_events(event):
                    on_event(ev)
            for line in _describe_event(event):
                print(line)
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"\n{BOLD}RUN ABORTED{RESET} — {error}\nSalvaging partial results.\n")

    final = await runner.session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session.id
    )
    state = final.state

    filed = [f for d in DESKS for f in state.get(f"flags:{d}", [])]
    verdicts = {
        f["flag_id"]: state[f"verdicts:{f['flag_id']}"]
        for f in filed
        if f"verdicts:{f['flag_id']}" in state
    }
    if "verified_flags" in state:
        kept, rejected = state["verified_flags"], state.get("rejected_flags", [])
    else:  # verification did not run (aborted run) — fall back, fail open
        kept, rejected = apply_verdicts(filed, verdicts)
    adjudication_notes: list[str] = []
    if plan := state.get("adjudication"):
        kept, adjudication_notes = adjudicator.apply_plan(kept, plan)
    kept.sort(key=lambda f: SEV_ORDER.get(f["severity"], 9))

    page_count = scenes[-1]["page"] if scenes else None
    the_report = report_mod.build_report(title, kept, page_count=page_count)

    record = {
        "script_title": title,
        "script_path": str(script_path),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - t0, 1),
        "error": error,
        "scenes": len(scenes),
        "entities": state.get("triage", {}).get("entities", []),
        "flags": kept,
        "rejected_flags": rejected,
        "verdicts": verdicts,
        "report": the_report,
        "adjudication_notes": adjudication_notes,
        "open_questions": {d: state.get(f"open_questions:{d}", []) for d in DESKS},
        "research_budget_left": {d: state.get(f"research_budget:{d}") for d in DESKS},
        "research": {
            k: v for k, v in state.items() if isinstance(k, str) and k.startswith("research:")
        },
    }
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

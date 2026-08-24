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

from google.adk.agents import SequentialAgent  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from greenlight import parser  # noqa: E402
from greenlight.agents import clearance_counsel, triage  # noqa: E402

APP_NAME = "greenlight"
USER_ID = "producer"
DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"

SEV_ORDER = {"BLOCKER": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "FYI": 4}


def build_root_agent() -> SequentialAgent:
    return SequentialAgent(
        name="greenlight_pipeline",
        description="Screenplay clearance: triage then the gatekeeper desks.",
        sub_agents=[triage.agent, clearance_counsel.agent],
    )


def _initial_state(text: str, scenes: list[dict[str, Any]], research_budget: int) -> dict[str, Any]:
    scene_index = "\n".join(f"{s['scene_id']}  p{s['page']:>2}  {s['heading']}" for s in scenes)
    return {
        "script_text": text,
        "scenes": scenes,
        "script_annotated": parser.annotated_script(text, scenes),
        "scene_index": scene_index,
        "research_budget": research_budget,
        "flag_seq": 0,
    }


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


async def run(script_path: str | Path, research_budget: int = 10) -> dict[str, Any]:
    source = Path(script_path).read_text()
    meta, scenes = parser.parse_fountain(source)
    title = meta.get("title", Path(script_path).stem)
    print(f"\n{BOLD}GREENLIGHT{RESET} — {title}: {len(scenes)} scenes parsed\n")

    runner = InMemoryRunner(agent=build_root_agent(), app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        state=_initial_state(source, scenes, research_budget),
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
            for line in _describe_event(event):
                print(line)
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"\n{BOLD}RUN ABORTED{RESET} — {error}\nSalvaging partial results.\n")

    final = await runner.session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session.id
    )
    state = final.state

    flags = sorted(
        (f for d in ("clearance_counsel",) for f in state.get(f"flags:{d}", [])),
        key=lambda f: SEV_ORDER.get(f["severity"], 9),
    )
    record = {
        "script_title": title,
        "script_path": str(script_path),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - t0, 1),
        "error": error,
        "scenes": len(scenes),
        "entities": state.get("triage", {}).get("entities", []),
        "flags": flags,
        "open_questions": {d: state.get(f"open_questions:{d}", []) for d in ("clearance_counsel",)},
        "research_budget_left": state.get("research_budget"),
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
    print(
        f"\n{BOLD}=== {record['script_title']} — {len(record['flags'])} flags, "
        f"{len(record['entities'])} entities, {record['elapsed_s']}s ==={RESET}\n"
    )
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
    for desk, qs in record["open_questions"].items():
        for q in qs:
            print(f"{DIM}open question ({desk}): {q}{RESET}")

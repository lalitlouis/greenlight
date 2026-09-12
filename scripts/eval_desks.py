#!/usr/bin/env python3
"""Bounded fresh desk diagnostics; explicit --live, real Gemini/Parallel, no report."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CASES = {
    "clearance_clip": {
        "desk": "clearance_counsel",
        "entity_ids": ["E004"],
        "worklist": [
            {
                "entity_id": "E004",
                "work_item_id": "CC-W001",
                "note": "Assess the use of JAWS on the television in S002.",
            }
        ],
    },
    "safety_climax": {
        "desk": "safety_underwriter",
        "entity_ids": [],
        "worklist": [
            {
                "entity_id": "",
                "work_item_id": "SU-W001",
                "note": "Assess the depicted vessel fire, fireworks and adjacent skiff "
                "with a child at night in S009, S010 and S011.",
            }
        ],
    },
}
MAX_MODEL_CALLS = 12
MAX_RETRIEVAL_CALLS = 4
CASE_TIMEOUT_S = 360


def prepare_case(record, script, case_id):
    """Reuse exact parser coordinates; expected outcomes never enter desk state."""
    from greenlight.parser import parse_fountain
    from greenlight.pipeline import _initial_state

    digest = hashlib.sha256(script.encode()).hexdigest()
    if digest != record["draft"]["sha256"]:
        raise ValueError("screenplay differs from source record")
    _, scenes = parse_fountain(script)
    coordinates = {
        s["scene_id"]: {k: s.get(k, "") for k in ("heading", "page", "number")} for s in scenes
    }
    if len(scenes) != record["scenes"] or coordinates != record["scene_meta"]:
        raise ValueError("parser coordinates differ from source record")
    case = CASES[case_id]
    entities = [e for e in record["entities"] if e["entity_id"] in case["entity_ids"]]
    if {e["entity_id"] for e in entities} != set(case["entity_ids"]):
        raise ValueError("missing assigned entity")
    # E004 is a pinned case identity, not a general-purpose screenplay selector.
    if case_id == "clearance_clip" and entities[0]["surface"] != "JAWS":
        raise ValueError("source entity no longer matches this case")
    state = _initial_state(
        script, scenes, {case["desk"]: MAX_RETRIEVAL_CALLS}, "", title=record["script_title"]
    )
    state["triage"] = {"entities": entities, case["desk"]: case["worklist"]}
    state[f"deep_used:{case['desk']}"] = 2  # disclosed evaluation cap; no paid Task API
    return state


def mechanical_errors(state, case_id, error):
    """Completion only; a disposed work item says nothing about semantic accuracy."""
    from greenlight.tools.toolbelt import desk_work_items_done

    case = CASES[case_id]
    problems = [error] if error else []
    expected = {w["work_item_id"] for w in case["worklist"]}
    if expected - desk_work_items_done(state, case["desk"]):
        problems.append("assigned work item lacks a disposition")
    return problems


class RetrievalRecorder:
    """Hard logical-call cap, including failures/refunds; record raw live receipts."""

    def __init__(self, checkpoint):
        import threading

        self.checkpoint = checkpoint
        self.calls = []
        self.lock = threading.Lock()

    def save(self):
        self.checkpoint.write_text(json.dumps(self.calls, indent=2) + "\n")

    def wrap(self, name, function):
        def recorded(*args, **kwargs):
            with self.lock:
                if len(self.calls) >= MAX_RETRIEVAL_CALLS:
                    raise RuntimeError("evaluation retrieval cap reached")
                call = {"api": name, "args": args, "kwargs": kwargs, "status": "running"}
                self.calls.append(call)
                self.save()
            started = time.monotonic()
            try:
                response = function(*args, **kwargs)
                with self.lock:
                    call.update(status="returned", response=response)
                return response
            except Exception as exc:
                with self.lock:
                    call.update(status="error", error=type(exc).__name__)
                raise
            finally:
                with self.lock:
                    call["elapsed_s"] = round(time.monotonic() - started, 2)
                    self.save()

        return recorded


async def evaluate(args):
    from google.adk.agents.run_config import RunConfig
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from greenlight.agents import clearance_counsel, safety_underwriter
    from greenlight.agents.common import make_desk
    from greenlight.costing import accumulate_usage, usage_cost_usd
    from greenlight.models import FLASH_MODEL
    from greenlight.tools import toolbelt

    source_bytes = args.record.read_bytes()
    record = json.loads(source_bytes)
    script = args.script.read_text()
    state = prepare_case(record, script, args.case)
    case = CASES[args.case]
    clearance = case["desk"] == "clearance_counsel"
    agent = make_desk(
        name="clearance_counsel__b1" if clearance else case["desk"],
        description="Assigned desk diagnostic worklist.",
        instruction=clearance_counsel.INSTRUCTION if clearance else safety_underwriter.INSTRUCTION,
        max_iterations=14 if clearance else 8,
        batch=0 if clearance else None,
    )
    runner = InMemoryRunner(agent=agent, app_name="greenlight_desk_eval")
    session = await runner.session_service.create_session(
        app_name=runner.app_name, user_id="diagnostic", state=state
    )
    tracked = RetrievalRecorder(args.output.with_suffix(".retrieval.json"))
    result = {
        "kind": "isolated_desk_diagnostic",
        "case": args.case,
        "model": FLASH_MODEL,
        "build": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_run_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "draft": record["draft"],
        "script_title": record["script_title"],
        "limits": {
            "model_calls": args.model_call_cap,
            "retrieval_calls": MAX_RETRIEVAL_CALLS,
            "deadline_s": CASE_TIMEOUT_S,
            "deep_research": False,
            "durable_cache": False,
        },
        "events": [],
        "status": "running",
        "gemini_usage": {},
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")

    async def consume():
        async for event in runner.run_async(
            user_id="diagnostic",
            session_id=session.id,
            new_message=types.Content(
                role="user",
                parts=[types.Part(text="Complete your assigned desk worklist on this screenplay.")],
            ),
            run_config=RunConfig(max_llm_calls=args.model_call_cap),
        ):
            accumulate_usage(result["gemini_usage"], event)
            result["events"].append(event.model_dump(mode="json", exclude_none=True))
            args.output.write_text(json.dumps(result, indent=2) + "\n")
            names = [
                p.function_call.name
                for p in (event.content.parts if event.content else [])
                if p.function_call
            ]
            print(args.case, len(result["events"]), ",".join(names) or "response", flush=True)

    started = time.monotonic()
    error = None
    # Fresh retrieval in this explicit diagnostic only; production defaults stay live
    # with their normal shared cache. No staging GCS reads/writes from the harness.
    with (
        patch.object(toolbelt, "_durable_cache_load", return_value=None),
        patch.object(toolbelt, "_durable_cache_store", return_value=None),
        patch.object(toolbelt, "_live_search", tracked.wrap("search", toolbelt._live_search)),
        patch.object(toolbelt, "_live_extract", tracked.wrap("extract", toolbelt._live_extract)),
        patch.object(toolbelt, "_live_task", side_effect=RuntimeError("Task API disabled in eval")),
    ):
        try:
            await asyncio.wait_for(consume(), timeout=CASE_TIMEOUT_S)
        except Exception as exc:
            error = type(exc).__name__
    final = await runner.session_service.get_session(
        app_name=runner.app_name, user_id="diagnostic", session_id=session.id
    )
    state = final.state
    problems = mechanical_errors(state, args.case, error)
    result.update(
        status="incomplete" if problems else "completed_unreviewed",
        error=error,
        elapsed_s=round(time.monotonic() - started, 2),
        mechanical_errors=problems,
        flags=toolbelt.desk_flags(state, case["desk"]),
        rejected_flags=[],
        open_questions=toolbelt.desk_open_questions(state, case["desk"]),
        cleared=toolbelt.desk_cleared(state, case["desk"]),
        state=state,
        scenes=state["scenes"],
        retrieval=tracked.calls,
        gemini_cost_estimate_usd=usage_cost_usd(result["gemini_usage"], 0),
        accuracy_pass=None,
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps({k: result[k] for k in ("status", "elapsed_s", "mechanical_errors")}), flush=True
    )
    await runner.close()
    return int(bool(problems))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument(
        "--model-call-cap",
        type=int,
        choices=(12, 20),
        default=MAX_MODEL_CALLS,
        help="explicit diagnostic model budget; production desk limits are unchanged",
    )
    parser.add_argument("--record", type=Path, default=ROOT / "runs/run_20260911_015915.json")
    parser.add_argument("--script", type=Path, default=ROOT / "fixtures/slack_tide.fountain")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.live:
        parser.error("requires --live; this runs metered Gemini and Parallel calls")
    if args.output.exists() or args.output.with_suffix(".retrieval.json").exists():
        parser.error("refusing to overwrite prior evidence")
    return asyncio.run(evaluate(args))


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    sys.exit(main())

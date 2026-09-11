#!/usr/bin/env python3
"""Targeted paid verification of saved failures; no full desk run or new retrieval.

Explicit --live opt-in. Uses the saved original excerpts and matching screenplay;
leaves the source record unchanged. Output is an audit artifact, not a new report.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from greenlight import parser  # noqa: E402
from greenlight.agents.evidence_review import (  # noqa: E402
    checked_verdict,
    repair_partial,
    review_incomplete,
)
from greenlight.agents.verification import (  # noqa: E402
    _RETRY_HTTP,
    EvidenceVerdict,
    _call_verifier_once,
    _scene_context,
    _search_context,
    apply_verdicts,
    call_verifier,
)
from greenlight.costing import accumulate_usage, usage_cost_usd  # noqa: E402
from greenlight.models import FLASH_MODEL  # noqa: E402


def resumable_audit(artifact, source_bytes, flag):
    """Reuse only a completed initial PARTIAL audit from an interrupted same-source case."""
    if artifact["source_run_sha256"] != hashlib.sha256(source_bytes).hexdigest():
        raise ValueError("resume artifact is for a different source record")
    result = next((r for r in artifact["results"] if r["flag_id"] == flag["flag_id"]), None)
    if not result or result.get("error") != "TimeoutError":
        raise ValueError("only interrupted cases can be resumed")
    first = next(
        (
            r
            for r in artifact["responses"]
            if r["flag_id"] == flag["flag_id"] and r["schema"] == "EvidenceVerdict"
        ),
        None,
    )
    if first:
        verdict = checked_verdict(
            EvidenceVerdict.model_validate_json(first["text"]).model_dump(), flag
        )
        if verdict["verdict"] == "PARTIAL":
            return verdict
    return None  # the first audit never returned; restart this case only


async def evaluate(args):  # noqa: PLR0915 - linear, bounded evaluation with resume/accounting
    from google import genai

    source_bytes = args.record.read_bytes()
    record = json.loads(source_bytes)
    script = args.script.read_text()
    if hashlib.sha256(script.encode()).hexdigest() != record["draft"]["sha256"]:
        raise ValueError("screenplay hash does not match the saved run")
    flags_by_id = {f["flag_id"]: f for f in record["flags"]}
    flags = [flags_by_id[fid] for fid in args.flags]
    resume = json.loads(args.resume_from.read_text()) if args.resume_from else None
    resumed = (
        {f["flag_id"]: resumable_audit(resume, source_bytes, f) for f in flags} if resume else {}
    )
    if len(flags) > 6 or len(set(args.flags)) != len(flags):
        raise ValueError("select at most six distinct findings")
    _, scenes = parser.parse_fountain(script)
    state = {"script_text": script, "scenes": scenes}
    usage = {}
    calls = 0
    responses = []
    current_flag_id = ""
    client = genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        http_options=_RETRY_HTTP,
    )

    async def generate_content(**kwargs):
        nonlocal calls
        calls += 1
        schema_name = kwargs["config"].response_schema.__name__
        print(f"{current_flag_id} call {calls}: {schema_name}", flush=True)
        response = await client.aio.models.generate_content(**kwargs)
        accumulate_usage(usage, response)
        responses.append(
            {
                "flag_id": current_flag_id,
                "schema": schema_name,
                "text": response.text,
                "usage_available": getattr(response, "usage_metadata", None) is not None,
            }
        )
        return response

    tracked = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    results = []
    started = time.monotonic()
    try:
        for flag in flags:
            current_flag_id = flag["flag_id"]
            began = time.monotonic()
            try:
                context, search = _scene_context(flag, state), _search_context(flag, state)
                if initial := resumed.get(flag["flag_id"]):
                    operation = repair_partial(
                        tracked, flag, context, search, initial, _call_verifier_once
                    )
                else:
                    operation = call_verifier(tracked, flag, context, search)
                verdict = await asyncio.wait_for(
                    operation,
                    timeout=240,
                )
                verdicts = {flag["flag_id"]: verdict}
                kept, dropped = apply_verdicts([flag], verdicts)
                result = {
                    "flag_id": flag["flag_id"],
                    "verdict": verdicts[flag["flag_id"]],
                    "kept": kept,
                    "dropped": dropped,
                    "verification_incomplete": review_incomplete(verdicts),
                }
            except Exception as exc:
                result = {"flag_id": flag["flag_id"], "error": type(exc).__name__}
            result["elapsed_s"] = round(time.monotonic() - began, 2)
            results.append(result)
            print(
                flag["flag_id"],
                result.get("error") or result["verdict"]["verdict"],
                f"{result['elapsed_s']}s",
                flush=True,
            )
    finally:
        await client.aio.aclose()
    artifact = {
        "source_run": str(args.record),
        "source_run_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_build": record.get("build"),
        "evaluated_build": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "model": FLASH_MODEL,
        "elapsed_s": round(time.monotonic() - started, 2),
        "calls": calls,
        "responses_with_usage": sum(r["usage_available"] for r in responses),
        "calls_without_returned_usage": calls - sum(r["usage_available"] for r in responses),
        "resumed_from": str(args.resume_from) if args.resume_from else None,
        "gemini_usage": usage,
        "estimated_cost_usd": usage_cost_usd(usage, 0),
        "manual_review": "pending; model approval is not an accuracy label",
        "results": results,
        "responses": responses,
    }
    args.output.write_text(json.dumps(artifact, indent=2) + "\n")
    print(f"Saved {args.output}; {calls} model calls, estimated ${artifact['estimated_cost_usd']}")
    return int(any(r.get("error") or r.get("verification_incomplete") for r in results))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--record", type=Path, default=Path("runs/run_20260911_demo.json"))
    p.add_argument("--script", type=Path, default=Path("fixtures/slack_tide.fountain"))
    p.add_argument("--flags", nargs="+", default=["F3002", "F3006", "F3008"])
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--resume-from", type=Path, help="resume only timed-out cases from a saved audit"
    )
    p.add_argument(
        "--live", action="store_true", help="spends money on up to 5 logical model calls per flag"
    )
    args = p.parse_args()
    if not args.live:
        p.error("--live is required: this targeted evaluation spends money")
    if args.output.exists() or args.output.resolve() in (
        args.record.resolve(),
        args.script.resolve(),
    ):
        p.error("output must be a new file, separate from the saved record and screenplay")
    load_dotenv()
    return asyncio.run(evaluate(args))


if __name__ == "__main__":
    raise SystemExit(main())

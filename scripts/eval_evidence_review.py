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

if __name__ == "__main__":
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from greenlight import parser
from greenlight.agents.evidence_review import (
    ClaimCheck,
    _support_problem,
    check_entailment,
    checked_verdict,
    corrected_flag,
    repair_partial,
    review_incomplete,
)
from greenlight.agents.verification import (
    _RETRY_HTTP,
    EvidenceVerdict,
    _call_verifier_once,
    _scene_context,
    _search_context,
    apply_verdicts,
    call_verifier,
)
from greenlight.costing import accumulate_usage, usage_cost_usd
from greenlight.models import FLASH_MODEL


class CallRecorder:
    """Persist stage timings even when a model call fails or is cancelled."""

    def __init__(self, client, checkpoint, max_calls):
        self.client = client
        self.checkpoint = checkpoint
        self.max_calls = max_calls
        self.current_id = ""
        self.usage = {}
        self.responses = []
        self.attempts = []
        self.aio = SimpleNamespace(models=self)

    def save(self):
        temporary = self.checkpoint.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.attempts, indent=2) + "\n")
        temporary.replace(self.checkpoint)

    async def generate_content(self, **kwargs):
        if len(self.attempts) >= self.max_calls:
            raise RuntimeError("evaluation logical-call budget exhausted")
        began = time.monotonic()
        schema_name = kwargs["config"].response_schema.__name__
        attempt = {
            "flag_id": self.current_id,
            "schema": schema_name,
            "status": "running",
            "input_chars": len(kwargs["contents"]),
            "input_sha256": hashlib.sha256(kwargs["contents"].encode()).hexdigest(),
        }
        self.attempts.append(attempt)
        self.save()
        print(f"{self.current_id} call {len(self.attempts)}: {schema_name}", flush=True)
        try:
            response = await self.client.aio.models.generate_content(**kwargs)
            accumulate_usage(self.usage, response)
            has_usage = getattr(response, "usage_metadata", None) is not None
            self.responses.append(
                {
                    "flag_id": self.current_id,
                    "schema": schema_name,
                    "text": response.text,
                    "usage_available": has_usage,
                }
            )
            attempt.update(status="returned", usage_available=has_usage)
            return response
        except asyncio.CancelledError:
            attempt.update(status="cancelled", error="CancelledError")
            raise
        except Exception as exc:
            attempt.update(status="error", error=type(exc).__name__)
            raise
        finally:
            attempt["elapsed_s"] = round(time.monotonic() - began, 2)
            self.save()
            print(
                f"{self.current_id} {schema_name}: {attempt['status']} {attempt['elapsed_s']}s",
                flush=True,
            )


def entailment_inputs(cases, source_bytes, script_context=""):
    """Build isolated claim probes from unchanged, hash-bound cached citations.

    Expected labels/reasons are evaluation-only and never passed to the reviewer.
    These developer-authored cases test excerpt entailment, not legal accuracy.
    """
    if cases["source_run_sha256"] != hashlib.sha256(source_bytes).hexdigest():
        raise ValueError("case source hash does not match the saved run")
    record = json.loads(source_bytes)
    if (
        script_context
        and hashlib.sha256(script_context.encode()).hexdigest() != record["draft"]["sha256"]
    ):
        raise ValueError("probe screenplay hash does not match the saved run")
    flags = {f["flag_id"]: f for f in record["flags"] + record.get("rejected_flags", [])}
    rows = cases["cases"]
    if not 1 <= len(rows) <= 6 or len({r["case_id"] for r in rows}) != len(rows):
        raise ValueError("select one to six distinct entailment cases")
    inputs = []
    for row in rows:
        field = row.get("field", "finding")
        flag = {
            **flags[row["source_flag_id"]],
            "flag_id": row["case_id"],
        }
        if field == "finding":
            flag["finding"] = row["claim"]
        elif field == "remedy":
            flag["remedy"] = {"detail": row["claim"], "action": row.get("action", "NO_ACTION")}
        else:
            raise ValueError("probe field must be finding or remedy")
        spans = row.get("support_spans")
        if spans is None:
            spans = [{"citation_number": row["citation_number"], "quote": row["quote"]}]
        check = {
            "field": field,
            "quote": row["claim"],
            "basis": row.get("basis", "source"),
            "status": "SUPPORTED",
            "reason": "Probe to be independently assessed",
            "citation_numbers": sorted({s["citation_number"] for s in spans}),
            "support_spans": spans,
            "script_spans": row.get("script_spans", []),
        }
        # This is an isolated secondary-stage probe, not approval of other fields.
        validated = ClaimCheck.model_validate(check)
        if _support_problem(validated, flag, script_context):
            raise ValueError("probe does not carry a valid excerpt receipt")
        verdict = {"verdict": "SUPPORTED", "claim_checks": [validated.model_dump()]}
        if not isinstance(row["expected_entailed"], bool):
            raise ValueError("expected entailment must be boolean")
        inputs.append((flag, verdict, row["expected_entailed"]))
    return inputs


def resumable_audit(artifact, source_bytes, flag, script_context=""):
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
            EvidenceVerdict.model_validate_json(first["text"]).model_dump(), flag, script_context
        )
        if verdict["verdict"] == "PARTIAL":
            return verdict
    return None  # the first audit never returned; restart this case only


def recheck_candidate(artifact, source_bytes, flag, script_context=""):
    """Complete only the skipped entailment stage after a deterministic audit fix."""
    if artifact["source_run_sha256"] != hashlib.sha256(source_bytes).hexdigest():
        raise ValueError("correction artifact is for a different source record")
    result = next(r for r in artifact["results"] if r["flag_id"] == flag["flag_id"])
    if not result["verdict"].get("evidence_review_unresolved"):
        raise ValueError("only unresolved corrections can be rechecked")
    trail = result["verdict"]["evidence_review"]
    if trail["after"].get("entailment_review"):
        raise ValueError("entailment already completed; do not replay a rejected judgement")
    candidate = corrected_flag(flag, trail["correction"])
    raw = next(
        r
        for r in reversed(artifact["responses"])
        if r["flag_id"] == flag["flag_id"] and r["schema"] == "EvidenceVerdict"
    )
    verdict = checked_verdict(
        EvidenceVerdict.model_validate_json(raw["text"]).model_dump(), candidate, script_context
    )
    if verdict["verdict"] != "SUPPORTED":
        raise ValueError("corrected candidate still fails its claim audit")
    return candidate, verdict


async def evaluate(args):  # noqa: PLR0915 - linear, bounded evaluation with resume/accounting
    from google import genai

    source_bytes = args.record.read_bytes()
    record = json.loads(source_bytes)
    script = args.script.read_text()
    if hashlib.sha256(script.encode()).hexdigest() != record["draft"]["sha256"]:
        raise ValueError("screenplay hash does not match the saved run")
    flags_by_id = {f["flag_id"]: f for f in record["flags"] + record.get("rejected_flags", [])}
    case_bytes = args.entailment_cases.read_bytes() if args.entailment_cases else None
    probes = entailment_inputs(json.loads(case_bytes), source_bytes, script) if case_bytes else []
    flags = [p[0] for p in probes] if probes else [flags_by_id[fid] for fid in args.flags]
    recheck = (
        json.loads(args.recheck_correction_from.read_text())
        if args.recheck_correction_from
        else None
    )
    rechecks = (
        [recheck_candidate(recheck, source_bytes, f, script) for f in flags] if recheck else []
    )
    if rechecks:
        flags = [r[0] for r in rechecks]
    resume = json.loads(args.resume_from.read_text()) if args.resume_from else None
    resumed = (
        {f["flag_id"]: resumable_audit(resume, source_bytes, f, script) for f in flags}
        if resume
        else {}
    )
    if len(flags) > 6 or (not probes and len(set(args.flags)) != len(flags)):
        raise ValueError("select at most six distinct findings")
    _, scenes = parser.parse_fountain(script)
    state = {"script_text": script, "scenes": scenes}
    client = genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        http_options=_RETRY_HTTP,
    )

    tracked = CallRecorder(
        client,
        args.output.with_suffix(".progress.json"),
        len(flags)
        if probes or rechecks
        else sum(3 if resumed.get(f["flag_id"]) else 5 for f in flags),
    )
    results = []
    started = time.monotonic()
    try:
        for index, flag in enumerate(flags):
            tracked.current_id = flag["flag_id"]
            began = time.monotonic()
            try:
                context, search = _scene_context(flag, state), _search_context(flag, state)
                if probes:
                    operation = check_entailment(tracked, flag, probes[index][1])
                elif rechecks:
                    operation = check_entailment(tracked, flag, rechecks[index][1])
                elif initial := resumed.get(flag["flag_id"]):
                    operation = repair_partial(
                        tracked, flag, context, search, initial, _call_verifier_once
                    )
                else:
                    operation = call_verifier(tracked, flag, context, search)
                verdict = await asyncio.wait_for(
                    operation,
                    timeout=240,
                )
                if probes:
                    checks = verdict.get("entailment_review", {}).get("checks", [])
                    actual = checks[0]["entailed"] if len(checks) == 1 else None
                    result = {
                        "flag_id": flag["flag_id"],
                        "verdict": verdict,
                        "expected_entailed": probes[index][2],
                        "actual_entailed": actual,
                        "passed": actual is probes[index][2],
                    }
                else:
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
    calls, responses, usage = len(tracked.attempts), tracked.responses, tracked.usage
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
        "rechecked_correction_from": str(args.recheck_correction_from) if rechecks else None,
        "entailment_cases": str(args.entailment_cases) if case_bytes else None,
        "entailment_cases_sha256": hashlib.sha256(case_bytes).hexdigest() if case_bytes else None,
        "attempts": tracked.attempts,
        "gemini_usage": usage,
        "estimated_cost_usd": usage_cost_usd(usage, 0),
        "manual_review": "pending; model approval is not an accuracy label",
        "results": results,
        "responses": responses,
    }
    args.output.write_text(json.dumps(artifact, indent=2) + "\n")
    print(f"Saved {args.output}; {calls} model calls, estimated ${artifact['estimated_cost_usd']}")
    return int(
        any(
            r.get("error") or r.get("verification_incomplete") or r.get("passed") is False
            for r in results
        )
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--record", type=Path, default=Path("runs/run_20260911_demo.json"))
    p.add_argument("--script", type=Path, default=Path("fixtures/slack_tide.fountain"))
    p.add_argument("--flags", nargs="+", default=["F3002", "F3006", "F3008"])
    p.add_argument("--output", type=Path, required=True)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--resume-from", type=Path, help="resume only timed-out cases from a saved audit"
    )
    mode.add_argument(
        "--entailment-cases",
        type=Path,
        help="one narrow review per hash-bound case; no repair or new report",
    )
    mode.add_argument(
        "--recheck-correction-from",
        type=Path,
        help="complete a skipped entailment stage after a deterministic audit fix",
    )
    p.add_argument(
        "--live", action="store_true", help="spends money on up to 5 logical model calls per flag"
    )
    args = p.parse_args()
    if not args.live:
        p.error("--live is required: this targeted evaluation spends money")
    if (
        args.output.exists()
        or args.output.with_suffix(".progress.json").exists()
        or args.output.resolve()
        in (
            args.record.resolve(),
            args.script.resolve(),
        )
    ):
        p.error("output must be a new file, separate from the saved record and screenplay")
    load_dotenv()
    return asyncio.run(evaluate(args))


if __name__ == "__main__":
    raise SystemExit(main())

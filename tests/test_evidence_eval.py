"""Offline guardrails for paid evidence evaluation; no live model calls."""

import asyncio
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from greenlight.agents.evidence_review import EntailmentResult, check_entailment

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "eval_evidence_review", ROOT / "scripts/eval_evidence_review.py"
)
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)


def test_probes_bind_original_excerpts_and_hide_expected_labels():
    cases = json.loads((ROOT / "fixtures/accuracy/entailment_cases_20260911.json").read_text())
    source = (ROOT / "runs/run_20260911_demo.json").read_bytes()
    inputs = evaluator.entailment_inputs(cases, source)
    prompts = []

    async def generate_content(**kwargs):
        prompts.append(kwargs["contents"])
        return SimpleNamespace(
            text=json.dumps(
                {"checks": [{"check_index": 0, "entailed": True, "reason": "Scripted"}]}
            )
        )

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    for flag, verdict, _ in inputs:
        asyncio.run(check_entailment(client, flag, verdict))
    for prompt, case in zip(prompts, cases["cases"], strict=True):
        payload = json.loads(prompt.split("\n\n", 1)[1])
        assert len(payload) == 1
        assert payload[0]["claim"] == case["claim"]
        assert "expected_entailed" not in prompt and case["label_reason"] not in prompt
        assert case["case_id"] not in prompt
    with pytest.raises(ValueError, match="source hash"):
        evaluator.entailment_inputs(cases, b"changed")
    forged = deepcopy(cases)
    forged["cases"][0]["quote"] = "A studio teacher is always mandatory."
    with pytest.raises(ValueError, match="valid excerpt receipt"):
        evaluator.entailment_inputs(forged, source)


def test_recheck_requires_matching_source_and_a_previously_skipped_stage():
    artifact = json.loads((ROOT / "fixtures/cassettes/firearms_timing_20260911.json").read_text())
    source = (ROOT / "runs/run_20260911_demo.json").read_bytes()
    flag = next(f for f in json.loads(source)["flags"] if f["flag_id"] == "F3008")
    candidate, verdict = evaluator.recheck_candidate(artifact, source, flag)
    assert verdict["verdict"] == "SUPPORTED"
    assert candidate["citations"] == flag["citations"]
    assert candidate["remedy"]["est_cost_usd"] is None
    with pytest.raises(ValueError, match="different source"):
        evaluator.recheck_candidate(artifact, b"changed", flag)
    artifact["results"][0]["verdict"]["evidence_review"]["after"]["entailment_review"] = {
        "checks": [{"entailed": False}]
    }
    with pytest.raises(ValueError, match="already completed"):
        evaluator.recheck_candidate(artifact, source, flag)


@pytest.mark.parametrize("name", ["applications", "edits_inquiries"])
def test_application_cases_use_real_script_receipts_and_never_send_expected_labels(name):
    cases = json.loads((ROOT / f"fixtures/accuracy/evidence_{name}_20260911.json").read_text())
    source = (ROOT / "runs/run_20260911_015915.json").read_bytes()
    script = (ROOT / "fixtures/slack_tide.fountain").read_text()
    inputs = evaluator.entailment_inputs(cases, source, script)
    prompts = []

    async def generate_content(**kwargs):
        prompts.append(kwargs["contents"])
        return SimpleNamespace(
            text=json.dumps(
                {
                    "checks": [
                        {"check_index": 0, "entailed": True, "reason": "Scripted wiring check"}
                    ]
                }
            )
        )

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    for flag, verdict, _ in inputs:
        asyncio.run(check_entailment(client, flag, verdict))
    assert len(prompts) == len(cases["cases"])
    for prompt, row in zip(prompts, cases["cases"], strict=True):
        payload = json.loads(prompt.split("\n\n", 1)[1])
        assert payload[0]["script_evidence"] == row["script_spans"]
        assert "expected_entailed" not in prompt and row["label_reason"] not in prompt
        assert all(s in script for s in payload[0]["script_evidence"])
    forged = deepcopy(cases)
    forged["cases"][0]["script_spans"] = ["A permit has already been obtained for this shoot."]
    with pytest.raises(ValueError, match="valid excerpt receipt"):
        evaluator.entailment_inputs(forged, source, script)
    with pytest.raises(ValueError, match="screenplay hash"):
        evaluator.entailment_inputs(cases, source, script + "altered")


@pytest.mark.parametrize("outcome", ["returned", "error", "cancelled"])
def test_call_recorder_persists_stage_status_and_enforces_budget(tmp_path, outcome):
    checkpoint = tmp_path / "calls.json"

    async def generate_content(**kwargs):
        assert json.loads(checkpoint.read_text())[0]["status"] == "running"
        if outcome == "error":
            raise RuntimeError("Private transport detail must not enter the artifact")
        if outcome == "cancelled":
            raise asyncio.CancelledError()
        return SimpleNamespace(
            text="{}",
            usage_metadata=SimpleNamespace(
                prompt_token_count=20, candidates_token_count=5, thoughts_token_count=3
            ),
        )

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    recorder = evaluator.CallRecorder(client, checkpoint, max_calls=1)
    recorder.current_id = "case"
    kwargs = {
        "contents": "test prompt",
        "config": SimpleNamespace(response_schema=EntailmentResult),
    }
    if outcome == "returned":
        asyncio.run(recorder.generate_content(**kwargs))
        assert recorder.usage["flash"]["output"] == 8
    else:
        expected = RuntimeError if outcome == "error" else asyncio.CancelledError
        with pytest.raises(expected):
            asyncio.run(recorder.generate_content(**kwargs))
        assert not recorder.responses and not recorder.usage
    attempts = json.loads(checkpoint.read_text())
    assert attempts[0]["status"] == outcome and attempts[0]["elapsed_s"] >= 0
    assert attempts[0]["schema"] == "EntailmentResult"
    assert "Private transport" not in checkpoint.read_text()
    with pytest.raises(RuntimeError, match="budget exhausted"):
        asyncio.run(recorder.generate_content(**kwargs))
    assert len(recorder.attempts) == 1

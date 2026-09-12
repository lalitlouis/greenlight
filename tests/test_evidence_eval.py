"""Offline guardrails for paid evidence evaluation; no live model calls."""

import asyncio
import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from greenlight.agents.evidence_review import EntailmentResult, check_entailment
from greenlight.agents.verification import apply_verdicts

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "eval_evidence_review", ROOT / "scripts/eval_evidence_review.py"
)
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)


def positive_check():
    return {
        "check_index": 0,
        "entailed": True,
        "reason": "Scripted wiring check",
        "scope_preserved": True,
        "requirements_supported": True,
        "scope_reason": "Scripted matching scope",
        "unsupported_parts": [],
    }


def test_probes_bind_original_excerpts_and_hide_expected_labels():
    cases = json.loads((ROOT / "fixtures/accuracy/entailment_cases_20260911.json").read_text())
    source = (ROOT / "runs/run_20260911_demo.json").read_bytes()
    inputs = evaluator.entailment_inputs(cases, source)
    prompts = []

    async def generate_content(**kwargs):
        prompts.append(kwargs["contents"])
        return SimpleNamespace(text=json.dumps({"checks": [positive_check()]}))

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    for flag, verdict, _ in inputs:
        asyncio.run(check_entailment(client, flag, verdict))
    for prompt, case in zip(prompts, cases["cases"], strict=True):
        payload = json.loads(prompt.rsplit("\n\n", 1)[1])
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


def test_prequalification_controls_include_useful_unknowns_and_structured_amounts():
    cases = json.loads(
        (ROOT / "fixtures/accuracy/prequalification_clearance_20260911.json").read_text()
    )
    source = (ROOT / "fixtures/cassettes/fresh_clearance_20260911.json").read_bytes()
    script = (ROOT / "fixtures/slack_tide.fountain").read_text()
    inputs = evaluator.entailment_inputs(cases, source, script)
    assert len(inputs) == 6 and sum(expected for _, _, expected in inputs) == 3
    amount_flag, amount_verdict, expected = inputs[4]
    assert amount_flag["remedy"]["est_cost_usd"] == [5000, 15000]
    assert amount_verdict["claim_checks"][0]["basis"] == "estimate" and not expected
    prompts = []

    async def generate_content(**kwargs):
        prompts.append(kwargs["contents"])
        return SimpleNamespace(text=json.dumps({"checks": [positive_check()]}))

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    for flag, verdict, _ in inputs:
        result = asyncio.run(check_entailment(client, flag, verdict))
        assert result["entailment_review"]["checks"][0]["entailed"]
    amount_payload = json.loads(prompts[4].rsplit("\n\n", 1)[1])[0]
    assert amount_payload["claim"] == "[5000,15000]"
    assert amount_payload["estimate_context"] == cases["cases"][4]["estimate_context"]
    assert all("expected_entailed" not in prompt for prompt in prompts)


@pytest.mark.parametrize("name", ["applications", "edits_inquiries"])
def test_application_cases_use_real_script_receipts_and_never_send_expected_labels(name):
    cases = json.loads((ROOT / f"fixtures/accuracy/evidence_{name}_20260911.json").read_text())
    source = (ROOT / "runs/run_20260911_015915.json").read_bytes()
    script = (ROOT / "fixtures/slack_tide.fountain").read_text()
    inputs = evaluator.entailment_inputs(cases, source, script)
    prompts = []

    async def generate_content(**kwargs):
        prompts.append(kwargs["contents"])
        return SimpleNamespace(text=json.dumps({"checks": [positive_check()]}))

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    for flag, verdict, _ in inputs:
        asyncio.run(check_entailment(client, flag, verdict))
    assert len(prompts) == len(cases["cases"])
    for prompt, row in zip(prompts, cases["cases"], strict=True):
        payload = json.loads(prompt.rsplit("\n\n", 1)[1])
        assert payload[0]["script_evidence"] == row["script_spans"]
        assert "expected_entailed" not in prompt and row["label_reason"] not in prompt
        assert all(s in script for s in payload[0]["script_evidence"])
    forged = deepcopy(cases)
    forged["cases"][0]["script_spans"] = ["A permit has already been obtained for this shoot."]
    with pytest.raises(ValueError, match="valid excerpt receipt"):
        evaluator.entailment_inputs(forged, source, script)
    with pytest.raises(ValueError, match="screenplay hash"):
        evaluator.entailment_inputs(cases, source, script + "altered")


@pytest.mark.parametrize("fid", ["F1001", "F2001"])
def test_skipped_application_review_reuses_unchanged_saved_candidate_and_audit(fid):
    artifact = json.loads(
        (ROOT / "fixtures/cassettes/evidence_application_repairs_20260911.json").read_text()
    )
    source = (ROOT / "runs/run_20260911_015915.json").read_bytes()
    record = json.loads(source)
    flag = next(f for f in record["flags"] + record["rejected_flags"] if f["flag_id"] == fid)
    script = (ROOT / "fixtures/slack_tide.fountain").read_text()
    candidate, verdict = evaluator.recheck_candidate(artifact, source, flag, script)
    assert verdict["verdict"] == "SUPPORTED"
    assert candidate["citations"] == flag["citations"]
    correction = next(r for r in artifact["results"] if r["flag_id"] == fid)["verdict"][
        "evidence_review"
    ]["correction"]
    assert candidate["remedy"]["detail"] == correction["remedy_detail"]
    assert candidate["remedy"]["est_cost_usd"] is None
    assert any(c["basis"] in {"application", "script_edit"} for c in verdict["claim_checks"])


@pytest.mark.parametrize(
    "verdict",
    [
        {"verdict": "PARTIAL", "reason": "one option is unsupported"},
        {"verdict": "UNSUPPORTED", "reason": "unsupported rule"},
        {"verdict": "SUPPORTED", "fail_open": True},
        {"verdict": "SUPPORTED", "content_filtered": True},
    ],
)
def test_negative_recheck_cannot_use_legacy_partial_acceptance(verdict):
    record = json.loads((ROOT / "runs/run_20260911_015915.json").read_text())
    flag = record["flags"][0]
    finished = evaluator.finish_recheck(verdict)
    assert finished["evidence_review_unresolved"]
    assert finished["verdict"] == "UNSUPPORTED"
    kept, dropped = apply_verdicts([flag], {flag["flag_id"]: finished})
    assert not kept and not dropped[0]["recoverable"]


def test_successful_recheck_keeps_the_reviewed_verdict():
    verdict = {"verdict": "SUPPORTED", "reason": "Supported by evidence"}
    assert evaluator.finish_recheck(verdict) is verdict


def interrupted_correction():
    """Build a checkpoint with current instructions, without binding tests to old prompts."""
    source = (
        ROOT / "fixtures/cassettes/prequalification_fresh_safety_20_20260911.json"
    ).read_bytes()
    flag = json.loads(source)["flags"][0]
    proposal = evaluator.SourceBoundRepair(
        finding="Scenes S009, S010 and S011 depict fire, fireworks and water immersion.",
        severity="HIGH",
        rule_ids=["csatf16_pyrotechnics_licenses_2018", "csatf17_water_devices_accounting"],
    )
    correction, _ = evaluator.bound_correction(proposal, evaluator.available_rules(flag))
    candidate = evaluator.corrected_flag(flag, correction)
    script = (ROOT / "fixtures/slack_tide.fountain").read_text()
    _, scenes = evaluator.parser.parse_fountain(script)
    state = {"script_text": script, "scenes": scenes}
    context, search = evaluator._scene_context(flag, state), evaluator._search_context(flag, state)
    artifact = {
        "source_run_sha256": hashlib.sha256(source).hexdigest(),
        "results": [{"flag_id": flag["flag_id"], "error": "TimeoutError"}],
        "responses": [
            {
                "flag_id": flag["flag_id"],
                "schema": "SourceBoundRepair",
                "text": proposal.model_dump_json(),
            }
        ],
        "attempts": [
            {"flag_id": flag["flag_id"], "schema": "SourceBoundRepair", "status": "returned"},
            {
                "flag_id": flag["flag_id"],
                "schema": "EvidenceVerdict",
                "status": "cancelled",
                "input_sha256": hashlib.sha256(
                    evaluator._blinded_prompt(candidate, context, search).encode()
                ).hexdigest(),
            },
        ],
    }
    return artifact, source, flag, context, search


def test_resume_candidate_requires_exact_input_and_unfinished_audit():
    artifact, source, flag, context, search = interrupted_correction()
    saved = evaluator.resumable_candidate(artifact, source, flag, context, search)
    assert len(saved["source_rules"]) == 2
    assert saved["candidate"]["citations"] == flag["citations"]
    assert saved["candidate"]["scene_ids"] == flag["scene_ids"]
    with pytest.raises(ValueError, match="different source"):
        evaluator.resumable_candidate(artifact, b"changed", flag, context, search)
    with pytest.raises(ValueError, match="input changed"):
        evaluator.resumable_candidate(artifact, source, flag, context + "changed", search)
    changed = deepcopy(artifact)
    proposal = json.loads(changed["responses"][0]["text"])
    proposal["finding"] += " Altered candidate."
    changed["responses"][0]["text"] = json.dumps(proposal)
    with pytest.raises(ValueError, match="input changed"):
        evaluator.resumable_candidate(changed, source, flag, context, search)
    artifact["attempts"][-1]["status"] = "returned"
    with pytest.raises(ValueError, match="do not replay"):
        evaluator.resumable_candidate(artifact, source, flag, context, search)
    artifact["results"][0] = {"flag_id": flag["flag_id"], "verdict": {"verdict": "UNSUPPORTED"}}
    with pytest.raises(ValueError, match="only interrupted"):
        evaluator.resumable_candidate(artifact, source, flag, context, search)


@pytest.mark.parametrize(
    "after",
    [
        {"verdict": "SUPPORTED"},
        {"verdict": "PARTIAL"},
        {"verdict": "UNSUPPORTED"},
        {"verdict": "SUPPORTED", "fail_open": True},
        {"verdict": "SUPPORTED", "content_filtered": True},
    ],
)
def test_resume_checks_saved_candidate_once_and_never_repairs_again(monkeypatch, after):
    artifact, source, flag, context, search = interrupted_correction()
    saved = evaluator.resumable_candidate(artifact, source, flag, context, search)
    calls = []

    async def verify_once(client, candidate, actual_context, actual_search):
        assert candidate == saved["candidate"]
        assert (actual_context, actual_search) == (context, search)
        calls.append(candidate)
        return {
            **after,
            "reason": "Scripted check of remaining stage",
            "support_span_version": evaluator.AUDIT_VERSION,
            "audit_input": evaluator.flag_fingerprint(candidate),
            "claim_checks": [],
        }

    monkeypatch.setattr(evaluator, "_call_verifier_once", verify_once)
    verdict = asyncio.run(evaluator.resume_candidate(None, flag, context, search, saved))
    assert len(calls) == 1
    kept, dropped = apply_verdicts([flag], {flag["flag_id"]: verdict})
    if after == {"verdict": "SUPPORTED"}:
        assert kept == [saved["candidate"]] and not dropped
        assert verdict["correction_input"] == evaluator.flag_fingerprint(flag)
    else:
        assert not kept and dropped
        assert verdict["evidence_review_unresolved"]


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

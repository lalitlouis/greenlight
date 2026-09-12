"""Offline checks of paid-eval isolation, evidence identity and spend bounds."""

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("desk_eval", ROOT / "scripts/eval_desks.py")
desk_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desk_eval)


@pytest.mark.parametrize("case_id", desk_eval.CASES)
def test_pinned_case_uses_script_without_saved_judgements(case_id):
    record = json.loads((ROOT / "runs/run_20260911_015915.json").read_text())
    original = deepcopy(record)
    script = (ROOT / "fixtures/slack_tide.fountain").read_text()
    state = desk_eval.prepare_case(record, script, case_id)
    assert len(state["scenes"]) == record["scenes"]
    assert {s["scene_id"] for s in state["scenes"]} == set(record["scene_meta"])
    assert record == original
    assert not any(key in state for key in ("flags", "verdicts", "report", "research"))
    assert list(state["triage"]) == ["entities", desk_eval.CASES[case_id]["desk"]]
    with pytest.raises(ValueError, match="screenplay differs"):
        desk_eval.prepare_case(record, script + "different", case_id)
    record["scene_meta"]["S001"]["page"] = 999
    with pytest.raises(ValueError, match="coordinates differ"):
        desk_eval.prepare_case(record, script, case_id)


def test_mechanical_completion_does_not_imply_semantic_pass():
    assert desk_eval.mechanical_errors({}, "safety_climax", None)
    state = {"wi_done:safety_underwriter": ["SU-W001"]}
    assert not desk_eval.mechanical_errors(state, "safety_climax", None)
    assert desk_eval.mechanical_errors(state, "safety_climax", "TimeoutError") == ["TimeoutError"]


def test_retrieval_limit_counts_failures_and_preserves_raw_receipts(tmp_path):
    tracker = desk_eval.RetrievalRecorder(tmp_path / "receipts.json")
    calls = []

    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            raise ValueError("offline scripted failure")
        return {"results": [{"excerpts": ["Raw **source** text."]}]}

    wrapped = tracker.wrap("search", fake)
    with pytest.raises(ValueError):
        wrapped("first", queries=["query"])
    for _ in range(desk_eval.MAX_RETRIEVAL_CALLS - 1):
        assert wrapped("next")["results"][0]["excerpts"] == ["Raw **source** text."]
    with pytest.raises(RuntimeError, match="cap reached"):
        wrapped("over budget")
    assert len(calls) == desk_eval.MAX_RETRIEVAL_CALLS
    saved = json.loads(tracker.checkpoint.read_text())
    assert saved[0]["status"] == "error"
    assert saved[-1]["response"]["results"][0]["excerpts"] == ["Raw **source** text."]


def test_scope_probes_pin_observed_false_approval_and_valid_source_receipts():
    import hashlib

    spec = importlib.util.spec_from_file_location(
        "scope_eval", ROOT / "scripts/eval_evidence_review.py"
    )
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    cases = json.loads((ROOT / "fixtures/accuracy/production_scope_20260911.json").read_text())
    source = (ROOT / "fixtures/cassettes/fresh_safety_20260911.json").read_bytes()
    script = (ROOT / "fixtures/slack_tide.fountain").read_text()
    inputs = evaluator.entailment_inputs(cases, source, script)
    assert len(inputs) == 6
    assert sum(expected for _, _, expected in inputs) == 2
    provenance = cases["observed_false_approval"]
    recorded = (ROOT / provenance["path"]).read_bytes()
    assert hashlib.sha256(recorded).hexdigest() == provenance["sha256"]
    verdict = json.loads(recorded)["results"][0]["verdict"]
    bad = next(c for c in cases["cases"] if c["case_id"] == provenance["case_id"])
    assert bad["expected_entailed"] is False
    index = next(i for i, c in enumerate(verdict["claim_checks"]) if c["quote"] == bad["claim"])
    assert (
        next(c for c in verdict["entailment_review"]["checks"] if c["check_index"] == index)[
            "entailed"
        ]
        is True
    )


@pytest.mark.parametrize("cap", [None, "20", "0", "9999"])
def test_cli_preserves_default_budget_and_rejects_unbounded_increases(monkeypatch, tmp_path, cap):
    args = [
        "eval_desks.py",
        "--live",
        "--case",
        "safety_climax",
        "--output",
        str(tmp_path / "out.json"),
    ]
    if cap is not None:
        args += ["--model-call-cap", cap]
    monkeypatch.setattr(sys, "argv", args)
    captured = []

    async def fake_evaluate(parsed):
        captured.append(parsed.model_call_cap)
        return 0

    monkeypatch.setattr(desk_eval, "evaluate", fake_evaluate)
    if cap in {"0", "9999"}:
        with pytest.raises(SystemExit) as exc:
            desk_eval.main()
        assert exc.value.code == 2 and not captured
    else:
        assert desk_eval.main() == 0
        assert captured == [12 if cap is None else 20]

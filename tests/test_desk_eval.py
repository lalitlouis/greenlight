"""Offline checks of paid-eval isolation, evidence identity and spend bounds."""

import importlib.util
import json
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

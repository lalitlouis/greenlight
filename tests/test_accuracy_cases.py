"""Original contrastive cases; no live AI or retrieval in these tests."""

import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "fixtures/accuracy/contrastive_cases.json").read_text())["cases"]
spec = importlib.util.spec_from_file_location(
    "eval_accuracy_cases", ROOT / "scripts/eval_accuracy_cases.py"
)
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_original_case_channels_and_count_inputs(case):
    assert evaluator.inventory_errors(case) == []


def test_cases_are_unique_paired_and_have_review_rubrics():
    assert len({c["id"] for c in CASES}) == len(CASES)
    assert set(Counter(c["pair"] for c in CASES).values()) == {2}
    assert all(c["review_expectations"] for c in CASES)


def _record(case, flags):
    return {
        "draft": {"sha256": hashlib.sha256(case["script"].encode()).hexdigest()},
        "error": None,
        "report": {"flags": flags, "verification_degraded": False},
        "verdicts": {f["flag_id"]: {"verdict": "SUPPORTED", "reason": "test"} for f in flags},
    }


def test_case_grader_rejects_wrong_draft_and_false_safety_blocker():
    case = CASES[0]
    flag = {
        "flag_id": "F1",
        "agent": case["desk"],
        "category": "stunt_pyro",
        "severity": "BLOCKER",
        "citations": [{"excerpt": "test evidence"}],
    }
    record = _record(case, [flag])
    assert any("BLOCKER" in e for e in evaluator.record_errors(case, record))
    flag["severity"] = "HIGH"
    assert evaluator.record_errors(case, record) == []
    record["draft"]["sha256"] = "unrelated"
    assert "draft hash" in evaluator.record_errors(case, record)[0]


def test_case_grader_does_not_pass_a_missing_or_unverified_hazard():
    case = CASES[0]
    assert any("absent" in e for e in evaluator.record_errors(case, _record(case, [])))
    flag = {
        "flag_id": "F1",
        "agent": case["desk"],
        "category": "stunt_pyro",
        "severity": "HIGH",
        "citations": [{"excerpt": "test evidence"}],
    }
    record = _record(case, [flag])
    record["verdicts"] = {}
    assert any("Unverified" in e for e in evaluator.record_errors(case, record))


def test_verifier_receives_shared_boundaries_and_real_scene_context():
    from greenlight.agents.evidence import PRODUCTION_EVIDENCE, RATINGS_EVIDENCE
    from greenlight.agents.verification import _blinded_prompt

    flag = {
        "finding": "A depicted fire needs specialist planning.",
        "severity": "HIGH",
        "category": "stunt_pyro",
        "scene_ids": ["S001"],
        "remedy": {"action": "ADD_SPECIALIST", "detail": "Confirm safe effects method."},
        "citations": [{"title": "Evidence", "excerpt": "test evidence"}],
    }
    prompt = _blinded_prompt(flag, CASES[0]["script"], "No quoted strings")
    assert PRODUCTION_EVIDENCE in prompt and RATINGS_EVIDENCE in prompt
    assert CASES[0]["script"] in prompt
    assert "{script_context}" not in prompt

"""Pin the fresh tattoo loss without weakening source/fact rejection boundaries."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from greenlight import parser
from greenlight.agents.evidence_review import (
    check_entailment,
    checked_verdict,
    corrected_flag,
    finish_repair,
    remedy_inquiry_correction,
)
from greenlight.agents.verification import (
    _call_verifier_once,
    _scene_context,
    _search_context,
    apply_verdicts,
    call_verifier,
)

ROOT = Path(__file__).resolve().parents[1]


def saved_repair(fid="F1010"):
    record = json.loads((ROOT / "runs/run_20260912_030306.json").read_text())
    flag = next(f for f in record["rejected_flags"] if f["flag_id"] == fid)
    trail = record["verdicts"][fid]["evidence_review"]
    script = (ROOT / "fixtures/slack_tide.fountain").read_text()
    _, scenes = parser.parse_fountain(script)
    state = {"script_text": script, "scenes": scenes}
    return flag, trail, _scene_context(flag, state), _search_context(flag, state)


def positive_review(verdict):
    return {
        "checks": [
            {
                "check_index": i,
                "entailed": True,
                "reason": "Scripted wiring check, not a semantic evaluation.",
                "scope_preserved": True,
                "requirements_supported": True,
                "scope_reason": "Scripted positive facets.",
                "named_rights_status": "not_asserted",
                "unsupported_parts": [],
            }
            for i, c in enumerate(verdict["claim_checks"])
            if c["status"] == "SUPPORTED" and c["field"] != "severity"
        ]
    }


class Client:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []
        self.aio = SimpleNamespace(models=self)

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(text=json.dumps(response))


def final_audit(trail, fallback):
    return {
        "verdict": "SUPPORTED",
        "reason": "Scripted full audit.",
        "failure_mode": "none",
        "claim_checks": [
            *[c for c in trail["after"]["claim_checks"] if c["field"] != "remedy"],
            {
                "field": "remedy",
                "quote": fallback["remedy_detail"],
                "basis": "inquiry",
                "status": "SUPPORTED",
                "reason": "Relevant missing-use/permission inquiry.",
                "citation_numbers": [],
                "support_spans": [],
                "script_spans": [],
            },
        ],
    }


def test_actual_tattoo_failure_retains_verified_warning_without_reusing_guarantee():
    flag, trail, context, search = saved_repair()
    before = deepcopy(flag)
    candidate = corrected_flag(flag, trail["correction"])
    fallback = remedy_inquiry_correction(candidate, trail["after"], context)
    assert fallback and fallback["finding"] == candidate["finding"]
    assert fallback["severity"] == candidate["severity"]
    assert fallback["remedy_action"] == "NO_ACTION"
    assert "eliminate copyright exposure" not in fallback["remedy_detail"]
    audit = final_audit(trail, fallback)
    client = Client(audit, positive_review(audit))
    result = asyncio.run(
        finish_repair(
            client,
            flag,
            context,
            search,
            trail["before"],
            trail["correction"],
            trail["after"],
            [],
            _call_verifier_once,
        )
    )
    assert len(client.calls) == 2 and result["verdict"] == "SUPPORTED"
    assert "eliminate copyright exposure" not in client.calls[0]["contents"]
    assert result["evidence_review"]["attempted_after"] == trail["after"]
    assert result["evidence_review"]["remedy_fallback"] is True
    kept, dropped = apply_verdicts([flag], {flag["flag_id"]: result})
    assert not dropped and kept[0]["finding"] == candidate["finding"]
    assert kept[0]["citations"] == flag["citations"] and flag == before
    assert kept[0]["remedy"]["est_cost_usd"] is None
    forged = deepcopy(result)
    forged["correction"]["remedy_detail"] += " This guarantees clearance."
    assert not apply_verdicts([flag], {flag["flag_id"]: forged})[0]


@pytest.mark.parametrize(
    "defect",
    [
        "finding",
        "severity",
        "source",
        "scene",
        "coverage",
        "fingerprint",
        "legacy",
        "missing_review",
        "missing_facet",
        "negative_scope",
        "owner",
        "duplicate",
        "filtered",
    ],
)
def test_remedy_recovery_cannot_promote_a_failed_or_incomplete_warning(defect):
    flag, trail, context, _ = saved_repair()
    candidate = corrected_flag(flag, trail["correction"])
    after = trail["after"]
    if defect in {"finding", "severity"}:
        next(c for c in after["claim_checks"] if c["field"] == defect)["status"] = "UNKNOWN"
    elif defect in {"source", "scene"}:
        for c in after["claim_checks"]:
            c["support_spans" if defect == "source" else "script_spans"] = []
    elif defect == "coverage":
        after["claim_checks"] = [c for c in after["claim_checks"] if c["basis"] != "script"]
    elif defect == "fingerprint":
        candidate["finding"] += " The artist has granted this production permission."
    elif defect == "legacy":
        after.pop("support_span_version")
    elif defect == "missing_review":
        after.pop("entailment_review")
    elif defect == "missing_facet":
        after["entailment_review"]["checks"][0].pop("requirements_supported")
    elif defect == "negative_scope":
        after["entailment_review"]["checks"][0]["scope_preserved"] = False
    elif defect == "owner":
        after["entailment_review"]["checks"][0]["named_rights_status"] = "unqualified_relationship"
    elif defect == "duplicate":
        after["entailment_review"]["checks"].append(after["entailment_review"]["checks"][0])
    else:
        after["content_filtered"] = True
    assert remedy_inquiry_correction(candidate, after, context) is None


@pytest.mark.parametrize("failure", ["unsupported", "partial", "unavailable"])
def test_final_inquiry_must_pass_both_reviews_without_another_repair(failure):
    flag, trail, context, search = saved_repair()
    candidate = corrected_flag(flag, trail["correction"])
    fallback = remedy_inquiry_correction(candidate, trail["after"], context)
    audit = final_audit(trail, fallback)
    secondary = positive_review(audit)
    if failure == "unsupported":
        audit["verdict"] = "UNSUPPORTED"
    elif failure == "partial":
        secondary["checks"][-1]["entailed"] = False
    else:
        secondary = RuntimeError("independent review unavailable")
    client = Client(audit, secondary)
    result = asyncio.run(
        finish_repair(
            client,
            flag,
            context,
            search,
            trail["before"],
            trail["correction"],
            trail["after"],
            [],
            _call_verifier_once,
        )
    )
    assert result["evidence_review_unresolved"]
    assert len(client.calls) <= 2
    assert not apply_verdicts([flag], {flag["flag_id"]: result})[0]


def test_runtime_has_one_generation_and_at_most_seven_checks_for_saved_failure():
    flag, trail, context, search = saved_repair()
    candidate = corrected_flag(flag, trail["correction"])
    fallback = remedy_inquiry_correction(candidate, trail["after"], context)
    audit = final_audit(trail, fallback)
    client = Client(
        trail["before"],
        positive_review(checked_verdict(trail["before"], flag, context)),
        trail["correction"],
        trail["after"],
        positive_review(checked_verdict(trail["after"], candidate, context)),
        audit,
        positive_review(audit),
    )
    result = asyncio.run(call_verifier(client, flag, context, search))
    assert result["verdict"] == "SUPPORTED" and len(client.calls) == 7
    assert [c["config"].response_schema.__name__ for c in client.calls].count("CorrectedClaim") == 1


def test_secondary_receives_raw_scene_context_without_promoting_production_assumptions():
    flag, trail, context, _ = saved_repair("F3004")
    candidate = corrected_flag(flag, trail["correction"])
    after = trail["after"]
    check = deepcopy(after["claim_checks"][0])
    check["status"] = "SUPPORTED"
    assert "funeral" in check["quote"] and not any("mourners" in s for s in check["script_spans"])
    verdict = {"verdict": "SUPPORTED", "claim_checks": [check]}
    client = Client(positive_review(verdict))
    asyncio.run(check_entailment(client, candidate, verdict, context))
    prompt = client.calls[0]["contents"]
    assert context in prompt and "The mourners in a loose crescent" in prompt
    assert after["reason"] not in prompt
    assert "cannot establish an external rule or actual production fact" in prompt
    assert json.loads(prompt.rsplit("\n\n", 1)[1])[0]["script_evidence"] == check["script_spans"]

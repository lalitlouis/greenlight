"""Cached SLACK TIDE failures and scripted model responses; no live services."""

import asyncio
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from greenlight.agents.evidence_review import (
    AUDIT_VERSION,
    PRODUCTION_INQUIRY,
    apply_estimate_audit,
    audit_fields,
    check_entailment,
    checked_verdict,
    corrected_flag,
    flag_fingerprint,
    review_incomplete,
)
from greenlight.agents.verification import (
    _apply_overturns,
    apply_verdicts,
    call_verifier,
    demotion_entries,
)
from greenlight.report import build_report
from greenlight.reverify import reverify_record

ROOT = Path(__file__).resolve().parents[1]


def saved_flag(fid="F3006"):
    record = json.loads((ROOT / "runs/run_20260911_demo.json").read_text())
    return next(f for f in record["flags"] if f["flag_id"] == fid)


def audit(flag, *, issue=None, verdict="SUPPORTED"):
    checks = [
        {
            "field": field,
            "quote": quote,
            "basis": "planning",
            "status": "SUPPORTED",
            "reason": "Supported by supplied evidence.",
            "citation_numbers": [1] if field != "severity" else [],
            "support_spans": [{"citation_number": 1, "quote": flag["citations"][0]["excerpt"]}]
            if field != "severity"
            else [],
        }
        for field, quote in (
            ("finding", flag["finding"]),
            ("remedy", flag["remedy"]["detail"]),
            ("severity", flag["severity"]),
        )
    ]
    if issue:
        checks.append(
            {
                "field": "finding" if issue == "minor performer" else "remedy",
                "quote": issue,
                "basis": "production",
                "status": "UNKNOWN",
                "reason": "Casting is unconfirmed; the remedy must retain its condition.",
                "citation_numbers": [],
                "support_spans": [],
            }
        )
    return {
        "verdict": verdict,
        "reason": "Overall review",
        "failure_mode": "none",
        "claim_checks": checks,
    }


def entailment(verdict):
    """Scripted positive secondary review; tests here establish mechanics only."""
    return {
        "checks": [
            {
                "check_index": i,
                "entailed": True,
                "reason": "Scripted positive review.",
                "scope_preserved": True,
                "requirements_supported": True,
                "scope_reason": "Scripted matching scope.",
                "unsupported_parts": [],
            }
            for i, check in enumerate(verdict["claim_checks"])
            if check["status"] == "SUPPORTED"
            and (check["support_spans"] or check["basis"] == "inquiry")
            and check["field"] != "severity"
            and check["quote"] != PRODUCTION_INQUIRY
        ]
    }


def correction():
    return {
        "finding": "Sam is a child character near the depicted rifle salute and vessel fire. "
        "Casting and staging are unknown; the depicted hazards need safety planning.",
        "remedy_detail": "Confirm casting and staging. If a minor performer is cast for "
        "hazardous activity, use a qualified stunt person as the cited guidance permits.",
        "remedy_action": "ADD_SPECIALIST",
        "severity": "HIGH",
    }


class Client:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.aio = SimpleNamespace(models=self)

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        res = self.responses.pop(0)
        if isinstance(res, Exception):
            raise res
        return SimpleNamespace(text=json.dumps(res), prompt_feedback=None)


def test_supported_label_cannot_override_unconfirmed_performer_check():
    flag = saved_flag("F3008")  # historical verdict was SUPPORTED
    verdict = checked_verdict(audit(flag, issue="minor performer"), flag)
    assert verdict["verdict"] == "PARTIAL"


@pytest.mark.parametrize(
    "problem", ["missing_field", "invented_quote", "bad_citation", "no_source"]
)
def test_audit_requires_real_field_and_citation_anchors(problem):
    flag = saved_flag()
    verdict = audit(flag)
    check = verdict["claim_checks"][0]
    if problem == "missing_field":
        verdict["claim_checks"].pop()
    elif problem == "invented_quote":
        check["quote"] = "This is not in the finding."
    elif problem == "bad_citation":
        check["citation_numbers"] = [99]
        check["support_spans"][0]["citation_number"] = 99
    else:
        check["basis"] = "source"
        check["support_spans"] = []
    if problem in {"missing_field", "invented_quote"}:
        with pytest.raises(ValueError):
            checked_verdict(verdict, flag)
    else:
        assert checked_verdict(verdict, flag)["verdict"] == "PARTIAL"


def test_corrected_remedy_is_reverified_without_original_review_and_stale_estimates():
    flag = saved_flag()
    before = deepcopy(flag)
    patch = correction()
    candidate = corrected_flag(flag, patch)
    initial = audit(flag, issue="Employ a certified Studio Teacher")
    client = Client(
        initial,
        entailment(initial),
        patch,
        audit(candidate),
        entailment(audit(candidate)),
    )
    verdict = asyncio.run(call_verifier(client, flag, "scene evidence", "search evidence"))
    assert len(client.calls) == 5
    assert "Return claim_checks" not in client.calls[2]["contents"]
    assert "Return the corrected finding" in client.calls[2]["contents"]
    assert (
        "Casting is unconfirmed; the remedy must retain its condition."
        not in (client.calls[-1]["contents"])
    )  # checker sees corrected claim + original evidence, not the repair argument
    kept, dropped = apply_verdicts([flag], {flag["flag_id"]: verdict})
    assert not dropped and len(kept) == 1
    repaired = kept[0]
    assert repaired["finding"] == patch["finding"]
    assert repaired["remedy"]["detail"] == patch["remedy_detail"]
    assert repaired["severity"] == "HIGH"  # no automatic severity downgrade
    assert repaired["citations"] == flag["citations"]
    assert repaired["scene_ids"] == flag["scene_ids"]
    assert repaired["remedy"]["est_cost_usd"] is None
    assert repaired["remedy"]["est_added_days"] is None
    assert flag == before  # stored source finding stays available for audit
    report = build_report("X", kept)
    assert report["counts"]["HIGH"] == 1 and report["greenlight_score"] == 92
    assert report["est_clearance_cost_usd"] is None and report["est_added_days"] is None


@pytest.mark.parametrize("failure", ["partial", "transport", "malformed", "unsupported"])
def test_repair_failure_is_unresolved_not_a_scored_partial_or_silent_clearance(failure):
    flag = saved_flag()
    patch = correction()
    initial = audit(flag, issue="Employ a certified Studio Teacher")
    if failure == "malformed":
        client = Client(initial, entailment(initial), {"finding": ""})
    else:
        after = (
            RuntimeError("offline failure")
            if failure == "transport"
            else audit(corrected_flag(flag, patch), verdict=failure.upper())
        )
        client = Client(
            initial,
            entailment(initial),
            patch,
            after,
            *([entailment(after)] if failure == "partial" else []),
        )
    verdict = asyncio.run(call_verifier(client, flag, "scene", "search"))
    verdicts = {flag["flag_id"]: verdict}
    kept, dropped = apply_verdicts([flag], verdicts)
    assert not kept and len(dropped) == 1
    assert not dropped[0]["recoverable"]  # no recursive repair or new search loop
    assert review_incomplete(verdicts)
    assert (
        len(client.calls)
        == {"malformed": 3, "transport": 4, "unsupported": 4, "partial": 5}[failure]
    )
    report = build_report("X", kept, verification_incomplete=review_incomplete(verdicts))
    assert report["greenlight_score"] is None and report["dimension_scores"] == {}
    assert report["verification_degraded"]
    questions = demotion_entries(dropped)["open_questions:safety_underwriter"]
    assert "F3006" in questions[0] and "S011" in questions[0]
    assert "Studio Teacher" not in questions[0]  # do not repeat rejected requirements
    _apply_overturns([flag], verdicts, {"script_text": "Sam is ten."})
    assert verdicts[flag["flag_id"]]["evidence_review_unresolved"]


def test_already_supported_claim_uses_one_narrow_span_review_and_is_unchanged():
    flag = saved_flag()
    flag["remedy"].update(est_cost_usd=None, est_added_days=None)
    client = Client(audit(flag), entailment(audit(flag)))
    verdict = asyncio.run(call_verifier(client, flag, "scene", "search"))
    kept, _ = apply_verdicts([flag], {flag["flag_id"]: verdict})
    assert kept == [flag] and len(client.calls) == 2


def test_repair_cannot_change_coordinates_or_be_reused_on_different_text():
    flag = saved_flag()
    with pytest.raises(ValueError, match="coordinates"):
        corrected_flag(flag, {**correction(), "finding": "The hazard in S099."})
    verdict = {
        "verdict": "SUPPORTED",
        "reason": "ok",
        "correction": correction(),
        "correction_input": flag_fingerprint(flag),
    }
    changed = {**flag, "finding": "A different claim."}
    verdicts = {flag["flag_id"]: verdict}
    kept, dropped = apply_verdicts([changed], verdicts)
    assert not kept and dropped and review_incomplete(verdicts)


def test_reverify_uses_repaired_text_and_retains_prior_unresolved_score_withhold():
    flag = {**saved_flag(), "verification_unavailable": True}
    candidate = corrected_flag(flag, correction())
    initial = audit(flag, issue="Employ a certified Studio Teacher")
    client = Client(
        initial,
        entailment(initial),
        correction(),
        audit(candidate),
        entailment(audit(candidate)),
    )

    async def verify(f):
        return await call_verifier(client, f, "scene", "search")

    record = {
        "script_title": "X",
        "flags": [flag],
        "desks_incomplete": [],
        "rejected_flags": [],
        "report": {},
        "verdicts": {"F3011": {"evidence_review_unresolved": True}},
    }
    summary = asyncio.run(reverify_record(record, "INT. ROOM - DAY\n\nAction.\n", verify=verify))
    assert summary["verified"] == 1
    assert record["flags"][0]["remedy"]["detail"] == correction()["remedy_detail"]
    assert not record["flags"][0].get("verification_unavailable")
    assert record["report"]["greenlight_score"] is None
    assert record["report"]["verification_degraded"]


def test_reverify_failed_repair_routes_to_open_question_and_withholds_score():
    flag = {**saved_flag(), "verification_unavailable": True}
    client = Client(audit(flag, issue="Employ a certified Studio Teacher"), {"finding": ""})

    async def verify(f):
        return await call_verifier(client, f, "scene", "search")

    record = {"script_title": "X", "flags": [flag], "verdicts": {}, "report": {}}
    summary = asyncio.run(reverify_record(record, "INT. ROOM - DAY\n\nAction.\n", verify=verify))
    assert summary["rejected"] == ["F3006"] and summary["verified"] == 0
    assert not record["flags"] and record["open_questions"]["safety_underwriter"]
    assert record["report"]["greenlight_score"] is None


def test_retry_cannot_score_a_repair_bound_to_another_claim():
    flag = {**saved_flag(), "verification_unavailable": True}

    async def verify(f):
        return {
            "verdict": "SUPPORTED",
            "reason": "ok",
            "correction": correction(),
            "correction_input": "wrong-input-hash",
        }

    record = {"script_title": "X", "flags": [flag], "verdicts": {}, "report": {}}
    asyncio.run(reverify_record(record, "INT. ROOM - DAY\n\nAction.\n", verify=verify))
    assert not record["flags"] and review_incomplete(record["verdicts"])
    assert record["report"]["greenlight_score"] is None


def test_eval_rejects_rendered_unresolved_claim_and_inflated_score():
    spec = importlib.util.spec_from_file_location(
        "eval_invariants", ROOT / "scripts/eval_invariants.py"
    )
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    record = json.loads((ROOT / "runs/run_20260911_demo.json").read_text())
    record["verdicts"]["F3006"]["evidence_review_unresolved"] = True

    def repair_checks():
        return {
            name: passed
            for name, passed, _ in evaluator.shared_invariants(record)
            if "unresolved evidence repairs" in name
        }

    assert len(repair_checks()) == 2 and not any(repair_checks().values())
    record["flags"] = [f for f in record["flags"] if f["flag_id"] != "F3006"]
    record["report"] = build_report("X", record["flags"], verification_incomplete=True)
    assert all(repair_checks().values())


@pytest.mark.parametrize("route", ["panel", "salvage"])
@pytest.mark.parametrize("repair_ok", [True, False])
def test_panel_and_salvage_share_repair_semantics(monkeypatch, route, repair_ok):
    from google import genai

    from greenlight import parser
    from greenlight.agents.verification import agent, verify_standalone

    flag = saved_flag()
    patch = correction()
    candidate = corrected_flag(flag, patch)
    initial = audit(flag, issue="Employ a certified Studio Teacher")
    client = Client(
        initial,
        entailment(initial),
        patch,
        audit(candidate, verdict="SUPPORTED" if repair_ok else "PARTIAL"),
        entailment(audit(candidate)),
    )
    monkeypatch.setattr(genai, "Client", lambda **kw: client)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "offline-test")
    script = (ROOT / "fixtures/slack_tide.fountain").read_text()
    _, scenes = parser.parse_fountain(script)
    state = {"script_text": script, "scenes": scenes, "flags:safety_underwriter": [flag]}
    if route == "salvage":
        verdicts = asyncio.run(verify_standalone([flag], state))
        kept, dropped = apply_verdicts([flag], verdicts)
    else:

        async def run():
            ctx = SimpleNamespace(session=SimpleNamespace(state=state), invocation_id="offline")
            events = [event async for event in agent._run_async_impl(ctx)]
            return events[-1].actions.state_delta

        result = asyncio.run(run())
        kept, dropped = result["verified_flags"], result["rejected_flags"]
        verdicts = {flag["flag_id"]: result["verdicts:" + flag["flag_id"]]}
    if repair_ok:
        assert kept[0]["finding"] == patch["finding"] and not dropped
    else:
        assert not kept and dropped and review_incomplete(verdicts)
    assert len(client.calls) == 5  # bounded; no research loop, even after a PARTIAL repair


@pytest.mark.parametrize(
    "basis", ["source", "planning", "script", "production", "application", "script_edit"]
)
def test_relabelling_a_prescription_does_not_bypass_support(basis):
    flag = saved_flag()
    verdict = audit(flag)
    remedy = verdict["claim_checks"][1]
    remedy.update(basis=basis, citation_numbers=[], support_spans=[])
    checked = checked_verdict(verdict, flag)
    assert checked["verdict"] == "PARTIAL"
    assert checked["claim_checks"][1]["status"] == "UNKNOWN"


@pytest.mark.parametrize("problem", ["invented", "paraphrase", "wrong_source", "wrong_index"])
def test_receipts_must_be_verbatim_in_their_own_source(problem):
    flag = saved_flag()
    verdict = audit(flag)
    check = verdict["claim_checks"][1]
    if problem == "invented":
        check["support_spans"][0]["quote"] = "All productions require a studio teacher."
    elif problem == "paraphrase":
        check["support_spans"][0]["quote"] = flag["citations"][0]["excerpt"].upper()
    elif problem == "wrong_source":
        check["support_spans"][0]["quote"] = flag["citations"][1]["excerpt"]
    else:
        check["support_spans"][0]["citation_number"] = 99
        check["citation_numbers"] = [99]
    checked = checked_verdict(verdict, flag)
    assert checked["verdict"] == "PARTIAL"  # correction, not a fake transport outage


def test_formatting_repair_keeps_raw_source_and_still_needs_entailment():
    flag = saved_flag()
    flag["citations"][0]["excerpt"] = "A **permit** is required only if filming here."
    original = deepcopy(flag)
    verdict = audit(flag)
    for check in verdict["claim_checks"][:2]:
        check["support_spans"][0]["quote"] = "A permit is required only if filming here."
    checked = checked_verdict(verdict, flag)
    assert flag == original
    assert checked["verdict"] == "SUPPORTED"  # mechanics only
    assert len(checked["support_span_reanchors"]) == 2
    for receipt in checked["support_span_reanchors"]:
        assert receipt["submitted_quote"] != receipt["raw_quote"]
        assert receipt["raw_quote"] == flag["citations"][0]["excerpt"]
    response = entailment(checked)
    response["checks"][0].update(entailed=False, reason="Source does not establish this duty.")
    client = Client(response)
    result = asyncio.run(check_entailment(client, flag, checked))
    assert result["verdict"] == "PARTIAL"
    assert "**permit**" in client.calls[0]["contents"]


def test_display_quote_cannot_borrow_another_citations_receipt():
    flag = saved_flag()
    flag["citations"][0]["excerpt"] = "Unrelated source."
    flag["citations"][1]["excerpt"] = "A **permit** is required."
    verdict = audit(flag)
    verdict["claim_checks"][0]["support_spans"][0]["quote"] = "A permit is required."
    assert checked_verdict(verdict, flag)["verdict"] == "PARTIAL"


def test_fixed_inquiry_is_allowed_but_an_unaudited_requirement_is_not():
    flag = saved_flag()
    flag["remedy"]["detail"] = PRODUCTION_INQUIRY
    verdict = audit(flag)
    verdict["claim_checks"][1].update(basis="inquiry", citation_numbers=[], support_spans=[])
    assert checked_verdict(verdict, flag)["verdict"] == "SUPPORTED"
    flag["remedy"]["detail"] += " Hire a certified studio teacher for every shoot."
    checked = checked_verdict(verdict, flag)
    assert checked["verdict"] == "PARTIAL"
    assert any("omitted" in check["reason"] for check in checked["claim_checks"])


@pytest.mark.parametrize("desk", ["ratings_board", "clearance_counsel", "territory_censor"])
def test_production_inquiry_cannot_repair_another_desks_finding(desk):
    flag = saved_flag()
    flag["agent"] = desk
    flag["remedy"]["detail"] = PRODUCTION_INQUIRY
    verdict = audit(flag)
    verdict["claim_checks"][1].update(basis="inquiry", citation_numbers=[], support_spans=[])
    result = checked_verdict(verdict, flag)
    assert result["verdict"] == "PARTIAL"
    assert "irrelevant" in result["claim_checks"][1]["reason"]


def test_inquiry_label_still_gets_independent_review_without_citations():
    flag = saved_flag()
    flag["remedy"]["detail"] = "Which mandatory studio teacher will you hire?"
    verdict = audit(flag)
    verdict["claim_checks"][1].update(basis="inquiry", citation_numbers=[], support_spans=[])
    result = checked_verdict(verdict, flag)
    response = entailment(result)
    response["checks"][1].update(entailed=False, reason="Concealed hiring requirement")
    client = Client(response)
    checked = asyncio.run(check_entailment(client, flag, result))
    assert checked["verdict"] == "PARTIAL"
    payload = json.loads(client.calls[0]["contents"].rsplit("\n\n", 1)[1])
    assert payload[1]["basis"] == "inquiry" and payload[1]["support"] == []
    assert payload[1]["desk"] == "safety_underwriter"


@pytest.mark.parametrize("basis", ["application", "script_edit", "risk_assessment"])
def test_applications_need_both_source_and_exact_script_receipts(basis):
    flag = saved_flag()
    verdict = audit(flag)
    check = verdict["claim_checks"][1]
    check.update(basis=basis, script_spans=["Sam is 10."])
    assert checked_verdict(verdict, flag)["verdict"] == "PARTIAL"
    assert checked_verdict(verdict, flag, "Sam is 10.")["verdict"] == "SUPPORTED"
    check["support_spans"] = []
    check["citation_numbers"] = []
    assert checked_verdict(verdict, flag, "Sam is 10.")["verdict"] == "PARTIAL"


@pytest.mark.parametrize("bad_result", ["missing", "duplicate", "unknown", "transport"])
def test_incomplete_entailment_review_withholds_score(bad_result):
    flag = saved_flag()
    verdict = checked_verdict(audit(flag), flag)
    response = entailment(verdict)
    if bad_result == "missing":
        response["checks"].pop()
    elif bad_result == "duplicate":
        response["checks"].append(response["checks"][0])
    elif bad_result == "unknown":
        response["checks"][0]["check_index"] = 999
    else:
        response = RuntimeError("service unavailable")
    client = Client(response)
    result = asyncio.run(check_entailment(client, flag, verdict))
    assert result["evidence_review_unresolved"]
    assert result["verdict"] == "UNSUPPORTED"


def test_exact_receipt_does_not_override_an_independent_entailment_rejection():
    flag = saved_flag("F3008")
    verdict = checked_verdict(audit(flag), flag)
    response = entailment(verdict)
    response["checks"][1].update(entailed=False, reason="Licenses are not firearms.")
    client = Client(response)
    result = asyncio.run(check_entailment(client, flag, verdict))
    assert result["verdict"] == "PARTIAL"
    assert result["claim_checks"][1]["status"] == "UNSUPPORTED"
    assert "Licenses are not firearms" in result["reason"]
    prompt = client.calls[0]["contents"]
    assert "excerpt_context" in prompt
    assert "Overall review" not in prompt and "Scripted positive review" not in prompt


def test_saved_minor_correction_supplies_attribution_without_prior_reasoning():
    artifact = json.loads(
        (ROOT / "fixtures/cassettes/support_spans_resume_20260911.json").read_text()
    )
    trail = artifact["results"][0]["verdict"]["evidence_review"]
    flag = saved_flag("F3006")
    candidate = corrected_flag(flag, trail["correction"])
    raw = next(r for r in artifact["responses"] if r["schema"] == "EvidenceVerdict")
    verdict = checked_verdict(json.loads(raw["text"]), candidate)
    assert verdict["verdict"] == "SUPPORTED"
    client = Client(entailment(verdict))  # verifies input isolation, not model accuracy
    asyncio.run(check_entailment(client, candidate, verdict))
    claims = json.loads(client.calls[0]["contents"].rsplit("\n\n", 1)[1])
    assert len(claims) == 1
    receipt = claims[0]["support"][0]
    source = flag["citations"][1]
    assert receipt["citation_number"] == 2
    assert receipt["source_attribution"] == {k: source[k] for k in ("title", "url")}
    assert receipt["excerpt_context"] == source["excerpt"]
    assert receipt["quote"] in source["excerpt"]
    assert set(claims[0]) == {
        "check_index",
        "claim",
        "claim_context",
        "support",
        "basis",
        "script_evidence",
    }
    assert claims[0]["script_evidence"] == []
    assert claims[0]["claim_context"] == candidate["finding"]  # context, not evidence


def test_source_metadata_cannot_replace_an_operative_excerpt_receipt():
    flag = saved_flag("F3006")
    verdict = audit(flag)
    # Even a real title/URL cannot be passed off as quoted source requirements.
    for metadata in ("title", "url"):
        forged = deepcopy(verdict)
        forged["claim_checks"][1]["support_spans"][0]["quote"] = flag["citations"][0][metadata]
        checked = checked_verdict(forged, flag)
        assert checked["verdict"] == "PARTIAL"
        assert checked["claim_checks"][1]["status"] == "UNKNOWN"


def test_saved_firearms_audit_can_leave_an_additive_join_between_atomic_checks():
    artifact = json.loads((ROOT / "fixtures/cassettes/firearms_timing_20260911.json").read_text())
    patch = artifact["results"][0]["verdict"]["evidence_review"]["correction"]
    candidate = corrected_flag(saved_flag("F3008"), patch)
    raw = next(r for r in artifact["responses"] if r["schema"] == "EvidenceVerdict")
    result = checked_verdict(json.loads(raw["text"]), candidate)
    assert result["verdict"] == "SUPPORTED"
    assert not any("omitted" in c["reason"] for c in result["claim_checks"])
    # Semantic review still has to approve both source clauses independently.
    assert sum(bool(c["support_spans"]) for c in result["claim_checks"]) == 2


@pytest.mark.parametrize("basis", ["source", "application", "script_edit", "inquiry"])
def test_optional_severity_receipt_does_not_request_literal_source_support_for_high(basis):
    flag = saved_flag()
    verdict = audit(flag)
    severity = verdict["claim_checks"][2]
    severity.update(
        basis=basis,
        citation_numbers=[1],
        support_spans=[{"citation_number": 1, "quote": flag["citations"][0]["excerpt"]}],
    )
    verdict = checked_verdict(verdict, flag)
    client = Client(entailment(verdict))
    result = asyncio.run(check_entailment(client, flag, verdict))
    payload = json.loads(client.calls[0]["contents"].rsplit("\n\n", 1)[1])
    assert {c["check_index"] for c in payload} == {0, 1}
    assert result["claim_checks"][2] == verdict["claim_checks"][2]
    assert result["verdict"] == "SUPPORTED"


@pytest.mark.parametrize(
    "gap",
    [
        "and",
        "and that",
        "or",
        "and/or",
        "unless",
        "and not",
        "and only if cast with minors",
        "and hire a studio teacher and",
    ],
)
def test_coverage_allows_internal_joins_but_not_missing_conditions_or_prescriptions(gap):
    flag = saved_flag()
    flag["finding"] = f"First clause {gap} second clause"
    verdict = audit(flag)
    check = verdict["claim_checks"][0]
    check["quote"] = "First clause"
    verdict["claim_checks"].append({**deepcopy(check), "quote": "second clause"})
    checked = checked_verdict(verdict, flag)
    assert (checked["verdict"] == "SUPPORTED") == (gap in {"and", "and that", "or", "and/or"})
    # The same words at either end are not a join between audited clauses.
    for text in (f"{gap} First clause", f"First clause {gap}"):
        flag["finding"] = text
        trimmed = audit(flag)
        trimmed["claim_checks"][0]["quote"] = "First clause"
        assert checked_verdict(trimmed, flag)["verdict"] == "PARTIAL"


def test_secondary_failure_cannot_reenter_an_unbounded_repair_loop():
    flag = saved_flag()
    before = audit(flag)
    failed = entailment(before)
    failed["checks"][1].update(entailed=False, reason="Prescription exceeds supplied text.")
    patch = correction()
    candidate = corrected_flag(flag, patch)
    after = audit(candidate)
    still_bad = entailment(after)
    still_bad["checks"][1].update(entailed=False, reason="Still unsupported.")
    client = Client(before, failed, patch, after, still_bad)
    result = asyncio.run(call_verifier(client, flag, "scene context", "script search"))
    assert result["evidence_review_unresolved"] and len(client.calls) == 5
    kept, dropped = apply_verdicts([flag], {flag["flag_id"]: result})
    assert not kept and not dropped[0]["recoverable"]


def test_clause_context_does_not_override_rejection_of_an_unsupported_alternative():
    flag = saved_flag()
    flag["remedy"]["detail"] = "Obtain permission or use royalty-free footage."
    verdict = audit(flag)
    check = verdict["claim_checks"][1]
    check["quote"] = "Obtain permission"
    verdict["claim_checks"].append({**deepcopy(check), "quote": "use royalty-free footage."})
    before = checked_verdict(verdict, flag)
    assert before["verdict"] == "SUPPORTED"
    response = entailment(before)
    response["checks"][-1].update(
        entailed=False, reason="Replacement permission is not established"
    )
    client = Client(response)
    after = asyncio.run(check_entailment(client, flag, before))
    assert after["verdict"] == "PARTIAL"
    payload = json.loads(client.calls[0]["contents"].rsplit("\n\n", 1)[1])
    remedies = [c for c in payload if "remedy_action" in c]
    assert all(c["claim_context"] == flag["remedy"]["detail"] for c in remedies)
    assert len(remedies) == 2


def test_field_based_severity_handling_does_not_override_a_negative_judgement():
    flag = saved_flag()
    verdict = audit(flag)
    verdict["claim_checks"][2].update(basis="application", status="UNKNOWN")
    assert checked_verdict(verdict, flag)["verdict"] == "PARTIAL"


def test_resume_reuses_only_a_timed_out_audit_with_matching_source():
    spec = importlib.util.spec_from_file_location(
        "eval_evidence_review", ROOT / "scripts/eval_evidence_review.py"
    )
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    artifact = json.loads((ROOT / "fixtures/cassettes/support_spans_20260911.json").read_text())
    source = (ROOT / "runs/run_20260911_demo.json").read_bytes()
    partial = evaluator.resumable_audit(artifact, source, saved_flag("F3006"))
    assert partial["verdict"] == "PARTIAL" and partial["support_span_version"] == AUDIT_VERSION
    assert evaluator.resumable_audit(artifact, source, saved_flag("F3008")) is None
    with pytest.raises(ValueError, match="different source"):
        evaluator.resumable_audit(artifact, b"changed source", saved_flag("F3006"))
    with pytest.raises(ValueError, match="only interrupted"):
        evaluator.resumable_audit(artifact, source, saved_flag("F3002"))


def test_structured_only_estimates_are_visible_and_withheld_without_losing_the_warning():
    flag = saved_flag()
    flag["remedy"].update(est_cost_usd=[4321, 6789], est_added_days=3)
    before = deepcopy(flag)
    client = Client(audit(flag), entailment(audit(flag)))  # first auditor omits numeric fields
    verdict = asyncio.run(call_verifier(client, flag, "scene", "search"))
    assert "[4321,6789]" in client.calls[0]["contents"]
    assert '"est_added_days": "3"' in client.calls[0]["contents"]
    assert verdict["verdict"] == "SUPPORTED" and len(client.calls) == 2
    assert set(verdict["estimate_exclusions"]) == {"est_cost_usd", "est_added_days"}
    kept, dropped = apply_verdicts([flag], {flag["flag_id"]: verdict})
    assert not dropped and kept[0]["finding"] == flag["finding"]
    assert kept[0]["remedy"]["detail"] == flag["remedy"]["detail"]
    assert kept[0]["remedy"]["est_cost_usd"] is None
    assert kept[0]["remedy"]["est_added_days"] is None
    assert flag == before
    report = build_report("X", kept, verification_incomplete=review_incomplete({"F": verdict}))
    assert report["greenlight_score"] is not None
    assert not report.get("verification_degraded")
    assert report["est_clearance_cost_usd"] is None and report["est_added_days"] is None


def estimate_checks(flag):
    """Scripted numeric evidence; does not establish real-world rate accuracy."""
    return [
        {
            "field": field,
            "quote": quote,
            "basis": "estimate",
            "status": "SUPPORTED",
            "reason": "Scripted estimate audit",
            "citation_numbers": [1],
            "support_spans": [{"citation_number": 1, "quote": flag["citations"][0]["excerpt"]}],
        }
        for field, quote in audit_fields(flag).items()
        if field.startswith("est_")
    ]


@pytest.mark.parametrize("stage", ["initial", "secondary"])
def test_a_rejected_numeric_estimate_does_not_require_rewriting_supported_prose(stage):
    flag = saved_flag()
    flag["remedy"].update(est_cost_usd=[100, 200], est_added_days=0)
    original = audit(flag)
    original["claim_checks"].extend(estimate_checks(flag))
    cost = next(c for c in original["claim_checks"] if c["field"] == "est_cost_usd")
    if stage == "initial":
        original["verdict"] = "PARTIAL"
        cost.update(status="UNKNOWN", reason="No applicable rate supports the range.")
    response = entailment(original)
    if stage == "secondary":
        response["checks"][-1].update(entailed=False, reason="No applicable rate supports cost.")
    client = Client(original, response)
    verdict = asyncio.run(call_verifier(client, flag, "scene", "search"))
    assert verdict["verdict"] == "SUPPORTED" and len(client.calls) == 2
    kept, dropped = apply_verdicts([flag], {flag["flag_id"]: verdict})
    assert not dropped and kept[0]["remedy"]["est_cost_usd"] is None
    assert kept[0]["remedy"]["est_added_days"] == 0  # independently accepted, not defaulted
    assert kept[0]["finding"] == flag["finding"]


def test_unknown_number_in_prose_still_requires_correction():
    flag = saved_flag()
    flag["remedy"]["detail"] = "The license will cost $5000."
    verdict = audit(flag)
    verdict["claim_checks"][1].update(status="UNKNOWN", reason="Unsupported price assertion.")
    assert checked_verdict(verdict, flag)["verdict"] == "PARTIAL"


def test_new_audit_is_bound_to_amounts_and_sources_while_legacy_records_are_unchanged():
    flag = saved_flag()
    original = deepcopy(flag)
    verdict = checked_verdict(audit(flag), flag)
    assert apply_estimate_audit(flag, {"support_span_version": 2}) == original
    changed = deepcopy(flag)
    changed["remedy"]["est_cost_usd"] = [1, 2]
    verdicts = {flag["flag_id"]: verdict}
    kept, dropped = apply_verdicts([changed], verdicts)
    assert not kept and dropped and review_incomplete(verdicts)
    assert flag == original


@pytest.mark.parametrize(
    "component", ["scope_preserved", "requirements_supported", "unsupported_parts"]
)
def test_failed_scope_or_duty_component_overrides_a_positive_boolean(component):
    flag = saved_flag()
    verdict = checked_verdict(audit(flag), flag)
    response = entailment(verdict)
    response["checks"][0][component] = (
        ["Unsupported open-flame alternative"] if component == "unsupported_parts" else False
    )
    client = Client(response)
    result = asyncio.run(check_entailment(client, flag, verdict))
    assert result["verdict"] == "PARTIAL"
    assert result["claim_checks"][0]["status"] == "UNSUPPORTED"
    assert result["entailment_review"]["checks"][0]["entailed"] is False


@pytest.mark.parametrize("component", ["scope_preserved", "requirements_supported", "scope_reason"])
def test_new_live_review_cannot_silently_omit_scope_checks(component):
    flag = saved_flag()
    verdict = checked_verdict(audit(flag), flag)
    response = entailment(verdict)
    response["checks"][0].pop(component)
    client = Client(response)
    result = asyncio.run(check_entailment(client, flag, verdict))
    assert result["evidence_review_unresolved"] and result["verdict"] == "UNSUPPORTED"


def test_partial_audit_positives_are_checked_before_the_correction_inherits_them():
    flag = saved_flag()
    initial = audit(flag, issue="Employ a certified Studio Teacher")
    first_review = entailment(initial)
    first_review["checks"][0].update(entailed=False, reason="The claimed relationship is absent.")
    patch = correction()
    candidate = corrected_flag(flag, patch)
    client = Client(initial, first_review, patch, audit(candidate), entailment(audit(candidate)))
    result = asyncio.run(call_verifier(client, flag, "scene", "search"))
    assert len(client.calls) == 5 and result["verdict"] == "SUPPORTED"
    repair_prompt = client.calls[2]["contents"]
    reviewed = json.loads(
        repair_prompt.split("\nVERIFICATION:\n", 1)[1].split("\nSCENE TEXT:", 1)[0]
    )
    assert reviewed["claim_checks"][0]["status"] == "UNSUPPORTED"
    assert "claimed relationship is absent" in reviewed["claim_checks"][0]["reason"]


@pytest.mark.parametrize("accepted", [True, False])
def test_source_bound_repair_still_requires_the_full_independent_acceptance_path(accepted):
    from greenlight.agents.source_rules import SourceBoundRepair, available_rules, bound_correction

    flag = json.loads((ROOT / "fixtures/cassettes/fresh_safety_20260911.json").read_text())[
        "flags"
    ][0]
    rules = available_rules(flag)
    proposal = SourceBoundRepair(
        finding="The sequence depicts fireworks and night-water exposure; "
        "the production method is unknown.",
        rule_ids=[r["rule_id"] for r in rules],
        severity="HIGH",
    )
    patch, _ = bound_correction(proposal, rules)
    candidate = corrected_flag(flag, patch)
    initial = audit(flag, issue="Marine Coordinator")
    final_review = entailment(audit(candidate))
    if not accepted:
        final_review["checks"][0].update(entailed=False, reason="Tested independent rejection.")
    client = Client(
        initial, entailment(initial), proposal.model_dump(), audit(candidate), final_review
    )
    verdict = asyncio.run(call_verifier(client, flag, "scene", "search"))
    assert len(client.calls) == 5
    assert client.calls[2]["config"].response_schema is SourceBoundRepair
    assert "SOURCE RULES" in client.calls[2]["contents"]
    kept, dropped = apply_verdicts([flag], {flag["flag_id"]: verdict})
    if accepted:
        assert not dropped and kept[0]["remedy"]["detail"] == patch["remedy_detail"]
        assert verdict["evidence_review"]["source_rules"] == rules
        assert kept[0]["citations"] == flag["citations"]
        assert kept[0]["scene_ids"] == flag["scene_ids"]
    else:
        assert not kept and dropped and verdict["evidence_review_unresolved"]


def test_redundant_citation_indexes_are_derived_from_valid_receipts_without_adding_evidence():
    artifact = json.loads(
        (
            ROOT / "fixtures/cassettes/prequalification_fresh_clearance_review_20260911.json"
        ).read_text()
    )
    source = json.loads(
        (ROOT / "fixtures/cassettes/prequalification_fresh_clearance_20260911.json").read_text()
    )
    flag = source["flags"][0]
    patch = artifact["results"][0]["verdict"]["evidence_review"]["correction"]
    candidate = corrected_flag(flag, patch)
    raw = next(r for r in reversed(artifact["responses"]) if r["schema"] == "EvidenceVerdict")
    audit_before = json.loads(raw["text"])
    original = deepcopy(candidate)
    checked = checked_verdict(
        audit_before, candidate, (ROOT / "fixtures/slack_tide.fountain").read_text()
    )
    assert candidate == original
    assert checked["verdict"] == "SUPPORTED"  # bookkeeping only; time scope still needs review
    repair = next(
        r for r in checked["citation_index_reanchors"] if r["submitted_indexes"] == [1, 2, 3]
    )
    assert repair["receipt_indexes"] == [2, 3]
    check = checked["claim_checks"][repair["check_index"]]
    assert check["citation_numbers"] == [2, 3]
    assert all(span["citation_number"] != 1 for span in check["support_spans"])
    response = entailment(checked)
    response["checks"][0].update(
        entailed=False, reason="Historical evidence cannot prove current scope."
    )
    result = asyncio.run(check_entailment(Client(response), candidate, checked))
    assert result["verdict"] == "PARTIAL"  # normalizing indexes cannot override a semantic failure

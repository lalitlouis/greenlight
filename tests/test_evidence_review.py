"""Cached SLACK TIDE failures and scripted model responses; no live services."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from greenlight.agents.evidence_review import (
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
            "citation_numbers": [],
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
            }
        )
    return {
        "verdict": verdict,
        "reason": "Overall review",
        "failure_mode": "none",
        "claim_checks": checks,
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
    else:
        check["basis"] = "source"
    with pytest.raises(ValueError):
        checked_verdict(verdict, flag)


def test_corrected_remedy_is_reverified_without_original_review_and_stale_estimates():
    flag = saved_flag()
    before = deepcopy(flag)
    patch = correction()
    candidate = corrected_flag(flag, patch)
    client = Client(audit(flag, issue="Employ a certified Studio Teacher"), patch, audit(candidate))
    verdict = asyncio.run(call_verifier(client, flag, "scene evidence", "search evidence"))
    assert len(client.calls) == 3
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
        client = Client(initial, {"finding": ""})
    else:
        after = (
            RuntimeError("offline failure")
            if failure == "transport"
            else audit(corrected_flag(flag, patch), verdict=failure.upper())
        )
        client = Client(initial, patch, after)
    verdict = asyncio.run(call_verifier(client, flag, "scene", "search"))
    verdicts = {flag["flag_id"]: verdict}
    kept, dropped = apply_verdicts([flag], verdicts)
    assert not kept and len(dropped) == 1
    assert not dropped[0]["recoverable"]  # no recursive repair or new search loop
    assert review_incomplete(verdicts)
    assert len(client.calls) <= 3
    report = build_report("X", kept, verification_incomplete=review_incomplete(verdicts))
    assert report["greenlight_score"] is None and report["dimension_scores"] == {}
    assert report["verification_degraded"]
    questions = demotion_entries(dropped)["open_questions:safety_underwriter"]
    assert "F3006" in questions[0] and "S011" in questions[0]
    assert "Studio Teacher" not in questions[0]  # do not repeat rejected requirements
    _apply_overturns([flag], verdicts, {"script_text": "Sam is ten."})
    assert verdicts[flag["flag_id"]]["evidence_review_unresolved"]


def test_already_supported_claim_uses_one_call_and_is_unchanged():
    flag = saved_flag()
    client = Client(audit(flag))
    verdict = asyncio.run(call_verifier(client, flag, "scene", "search"))
    kept, _ = apply_verdicts([flag], {flag["flag_id"]: verdict})
    assert kept == [flag] and len(client.calls) == 1


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
    client = Client(
        audit(flag, issue="Employ a certified Studio Teacher"), correction(), audit(candidate)
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


@pytest.mark.parametrize("route", ["panel", "salvage"])
@pytest.mark.parametrize("repair_ok", [True, False])
def test_panel_and_salvage_share_repair_semantics(monkeypatch, route, repair_ok):
    from google import genai

    from greenlight import parser
    from greenlight.agents.verification import agent, verify_standalone

    flag = saved_flag()
    patch = correction()
    candidate = corrected_flag(flag, patch)
    client = Client(
        audit(flag, issue="Employ a certified Studio Teacher"),
        patch,
        audit(candidate, verdict="SUPPORTED" if repair_ok else "PARTIAL"),
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
    assert len(client.calls) == 3  # no hidden extra repair/research loop

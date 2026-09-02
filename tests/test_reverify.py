"""Targeted re-verification (run-16): retry only the unverified findings and
recompute the score — never a full paid re-run for a transient."""

import asyncio

from greenlight.reverify import reverify_record

SCRIPT = "Title: T\n\nINT. A - DAY\n\nSTU\nHello there, friend.\n"


def _record():
    mk = lambda fid, unavailable: {  # noqa: E731
        "flag_id": fid,
        "agent": "ratings_board",
        "scene_ids": ["S001"],
        "entity_id": None,
        "severity": "MEDIUM",
        "category": "rating_language",
        "finding": "A finding.",
        "citations": [
            {
                "source_type": "web",
                "excerpt": "x",
                "url": None,
                "via": "local",
                "title": "",
                "retrieved_at": None,
            }
        ],
        "remedy": {
            "action": "REPLACE",
            "detail": "Do it.",
            "est_cost_usd": None,
            "est_added_days": None,
        },
        "confidence": 0.8,
        **({"verification_unavailable": True} if unavailable else {}),
    }
    return {
        "script_title": "T",
        "flags": [mk("F101", False), mk("F102", True), mk("F103", True)],
        "rejected_flags": [],
        "verdicts": {"F101": {"verdict": "SUPPORTED", "reason": "ok", "failure_mode": "none"}},
        "open_questions": {},
        "desks_incomplete": [],
        "report": {"greenlight_score": None, "page_count": 1, "rating_prediction": None},
    }


def test_reverify_clears_markers_rejects_and_scores():
    rec = _record()

    async def verify(flag):
        if flag["flag_id"] == "F102":
            return {"verdict": "SUPPORTED", "reason": "holds", "failure_mode": "none"}
        return {
            "verdict": "UNSUPPORTED",
            "reason": "excerpts do not establish the premise",
            "failure_mode": "premise_unsupported",
        }

    s = asyncio.run(reverify_record(rec, SCRIPT, verify=verify))
    assert s["retried"] == 2 and s["verified"] == 1 and s["rejected"] == ["F103"]
    assert not any(f.get("verification_unavailable") for f in rec["flags"])
    assert {f["flag_id"] for f in rec["flags"]} == {"F101", "F102"}
    assert rec["rejected_flags"] and rec["rejected_flags"][0]["flag_id"] == "F103"
    # the sourcing failure demoted to an open question, like the live pipeline
    assert any("F103" in q for q in rec["open_questions"].get("ratings_board", []))
    # with nothing unverified left, the score computes
    assert isinstance(rec["report"]["greenlight_score"], int)
    assert any(g["guard"] == "reverify" for g in rec["guard_manifest"])


def test_reverify_keeps_honest_withhold_when_still_down():
    rec = _record()

    async def verify(flag):
        raise RuntimeError("still down")

    s = asyncio.run(reverify_record(rec, SCRIPT, verify=verify))
    assert s["still_unavailable"] == 2 and s["verified"] == 0
    assert sum(1 for f in rec["flags"] if f.get("verification_unavailable")) == 2
    assert rec["report"]["greenlight_score"] is None  # withheld stands


def test_call_verifier_censored_fallback_caps_at_partial():
    """A prompt the platform filter blocks retries with the scene text withheld
    and judges the premise only — capped at PARTIAL, never full SUPPORTED
    without the script-fact check. Both-blocked fails open with the filter
    named (Wolf of Wall Street, 2026-09-01)."""
    import asyncio

    from greenlight.agents.verification import call_verifier

    class _Res:
        def __init__(self, text, blocked=False):
            self.text = text
            self.prompt_feedback = (
                type("FB", (), {"block_reason": "PROHIBITED_CONTENT"})() if blocked else None
            )

    class _Models:
        def __init__(self, responses):
            self._r = list(responses)

        async def generate_content(self, **kw):
            return self._r.pop(0)

    class _Client:
        def __init__(self, responses):
            self.aio = type("A", (), {"models": _Models(responses)})()

    flag = {
        "flag_id": "F101",
        "finding": "x",
        "citations": [],
        "remedy": {"action": "REPLACE", "detail": "y"},
        "scene_ids": [],
        "severity": "MEDIUM",
        "category": "rating_language",
    }
    ok = '{"verdict": "SUPPORTED", "reason": "premise holds", "failure_mode": "none"}'
    v = asyncio.run(call_verifier(_Client([_Res(None, blocked=True), _Res(ok)]), flag, "ctx", ""))
    assert v["verdict"] == "PARTIAL" and v["content_filtered"]
    assert "content filter" in v["reason"]

    v2 = asyncio.run(
        call_verifier(_Client([_Res(None, blocked=True), _Res(None, blocked=True)]), flag, "c", "")
    )
    assert v2["fail_open"] and v2["content_filtered"]


def test_reverify_counts_blocked_separately_and_keeps_withhold():
    rec = _record()

    async def verify(flag):
        return {
            "verdict": "SUPPORTED",
            "reason": "verifier unavailable — content filter",
            "fail_open": True,
            "content_filtered": True,
        }

    s = asyncio.run(reverify_record(rec, SCRIPT, verify=verify))
    assert s["blocked"] == 2 and s["verified"] == 0
    assert all(
        f.get("verification_blocked") for f in rec["flags"] if f.get("verification_unavailable")
    )
    assert rec["report"]["greenlight_score"] is None  # withheld stands, honestly labeled


def test_reverify_screens_rejections_with_the_overturn_guards_and_finalizes():
    """A rejection asserting the script lacks a line it contains is overturned
    exactly as the live panel would; the shared post-verification pass runs."""
    rec = _record()
    rec["flags"][1]["finding"] = "Stu says 'Hello there, friend.' in S001."
    rec["cleared"] = {"ratings_board": [{"entity_id": "", "reasoning": "Handled in F103."}]}

    async def verify(flag):
        if flag["flag_id"] == "F102":
            return {
                "verdict": "UNSUPPORTED",
                "reason": "The line 'Hello there, friend.' does not appear in the screenplay.",
                "failure_mode": "script_misstatement",
            }
        return {
            "verdict": "UNSUPPORTED",
            "reason": "excerpts do not establish the premise",
            "failure_mode": "premise_unsupported",
        }

    summary = asyncio.run(reverify_record(rec, SCRIPT, verify=verify))
    assert summary["verified"] == 1 and summary["rejected"] == ["F103"]
    assert rec["verdicts"]["F102"]["verdict"] == "SUPPORTED"
    assert rec["verdicts"]["F102"].get("overridden") is True
    assert any(m["guard"] == "overturn" and m["stage"] == "reverify" for m in rec["guard_manifest"])
    # the cleared row citing the now-rejected F103 is annotated (finalize ran)
    assert (
        "F103 (later rejected in verification — see Rejected)"
        in (rec["cleared"]["ratings_board"][0]["reasoning"])
    )
    assert "oq_followups" in rec


def test_reverify_reconciles_the_rating_panel_when_a_rating_flag_falls():
    rec = _record()
    rec["report"]["rating_prediction"] = {
        "predicted": "R",
        "target": "PG-13",
        "rationale": "for language and brief drug use",
        "beats_to_cut": ["Cut the F-words", "Trim the joint"],
        "comparables": [],
    }
    seen = {}

    async def verify(flag):
        return {
            "verdict": "UNSUPPORTED",
            "reason": "excerpts do not establish the premise",
            "failure_mode": "premise_unsupported",
        }

    async def reconcile(pred, kept, dropped):
        seen["dropped"] = [d["flag_id"] for d in dropped]
        return {"rationale": "for language", "beats_to_cut": ["Cut the F-words"]}

    asyncio.run(reverify_record(rec, SCRIPT, verify=verify, reconcile=reconcile))
    assert seen["dropped"] == ["F102", "F103"]
    pred = rec["report"]["rating_prediction"]
    assert pred["rationale"] == "for language"
    assert pred["beats_to_cut"] == ["Cut the F-words"]
    assert pred["reconciled_after_verification"] is True
    assert pred["pre_verification"]["beats_to_cut"] == ["Cut the F-words", "Trim the joint"]


def test_reverify_without_a_reconciler_says_so_on_the_manifest():
    rec = _record()
    rec["report"]["rating_prediction"] = {
        "predicted": "R",
        "target": "PG-13",
        "rationale": "for language",
        "beats_to_cut": ["Cut the F-words"],
        "comparables": [],
    }

    async def verify(flag):
        return {
            "verdict": "UNSUPPORTED",
            "reason": "excerpts do not establish the premise",
            "failure_mode": "premise_unsupported",
        }

    asyncio.run(reverify_record(rec, SCRIPT, verify=verify))
    assert any(
        m["guard"] == "rating_reconcile" and m["outcome"] == "not_run"
        for m in rec["guard_manifest"]
    )

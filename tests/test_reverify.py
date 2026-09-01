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

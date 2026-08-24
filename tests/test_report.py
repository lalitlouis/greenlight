"""Deterministic report assembly and verdict application. No API calls."""

from greenlight.agents.verification import apply_verdicts
from greenlight.report import build_report, greenlight_score


def make_flag(fid, severity, cost=None, days=None, agent="clearance_counsel"):
    return {
        "flag_id": fid,
        "agent": agent,
        "scene_ids": ["S001"],
        "entity_id": None,
        "severity": severity,
        "category": "test",
        "finding": "A finding.",
        "citations": [
            {
                "source_type": "web",
                "title": "t",
                "url": "https://example.com",
                "excerpt": "supporting text",
                "retrieved_at": None,
                "via": "parallel_search",
            }
        ],
        "remedy": {
            "action": "REPLACE",
            "detail": "Do the thing.",
            "est_cost_usd": cost,
            "est_added_days": days,
        },
        "confidence": 0.9,
    }


def test_score_is_deterministic_and_weighted():
    assert greenlight_score([]) == 100
    assert greenlight_score([make_flag("F101", "BLOCKER")]) == 70
    assert greenlight_score([make_flag("F101", "HIGH"), make_flag("F102", "MEDIUM")]) == 89
    many = [make_flag(f"F{i}", "BLOCKER") for i in range(101, 121)]
    assert 0 <= greenlight_score(many) <= 2  # dense scripts approach 0, never below
    # a BLOCKER always costs more than any single lesser flag
    assert greenlight_score([make_flag("F1", "BLOCKER")]) < greenlight_score(
        [make_flag("F1", "HIGH")]
    )


def test_build_report_validates_and_aggregates():
    flags = [
        make_flag("F101", "HIGH", cost=[1000, 5000], days=10),
        make_flag("F201", "MEDIUM", cost=[500, 2000], days=30, agent="ratings_board"),
        make_flag("F301", "FYI", agent="safety_underwriter"),
    ]
    rep = build_report("SLACK TIDE", flags, page_count=13)
    assert rep["greenlight_score"] == round(100 * 0.92 * 0.97)
    assert rep["counts"]["HIGH"] == 1 and rep["counts"]["BLOCKER"] == 0
    assert rep["by_agent"]["clearance_counsel"] == 1
    assert rep["est_clearance_cost_usd"] == [1500, 7000]
    assert rep["est_added_days"] == 30  # critical path, not a sum


def test_apply_verdicts_supported_and_missing_keep_flag():
    flags = [make_flag("F101", "HIGH"), make_flag("F102", "HIGH")]
    kept, rejected = apply_verdicts(flags, {"F101": {"verdict": "SUPPORTED", "reason": "ok"}})
    assert len(kept) == 2 and not rejected  # missing verdict fails open


def test_apply_verdicts_partial_caps_severity():
    kept, _ = apply_verdicts(
        [make_flag("F101", "BLOCKER")], {"F101": {"verdict": "PARTIAL", "reason": "narrower"}}
    )
    assert kept[0]["severity"] == "MEDIUM"
    assert kept[0]["finding"].startswith("[partially supported]")
    # a LOW flag is not promoted upward by the cap
    kept2, _ = apply_verdicts(
        [make_flag("F102", "LOW")], {"F102": {"verdict": "PARTIAL", "reason": "n"}}
    )
    assert kept2[0]["severity"] == "LOW"


def test_apply_verdicts_unsupported_rejects():
    kept, rejected = apply_verdicts(
        [make_flag("F101", "HIGH")], {"F101": {"verdict": "UNSUPPORTED", "reason": "off-topic"}}
    )
    assert not kept
    assert rejected[0]["rejection_reason"] == "off-topic"


def test_apply_plan_merges_duplicates_and_normalizes():
    from greenlight.agents.adjudicator import apply_plan

    flags = [
        make_flag("F401", "BLOCKER", agent="territory_censor"),
        make_flag("F402", "BLOCKER", agent="territory_censor"),
        make_flag("F301", "HIGH", agent="safety_underwriter"),
    ]
    plan = {
        "merges": [
            {
                "surviving_flag_id": "F401",
                "merged_flag_ids": ["F402"],
                "category": "territory_uae_illegal_acts",
                "severity": "BLOCKER",
                "rationale": "duplicate",
            }
        ],
        "conflicts": [{"flag_ids": ["F401", "F301"], "resolution": "cut before reshoot"}],
    }
    out, notes = apply_plan(flags, plan)
    ids = [f["flag_id"] for f in out]
    assert ids == ["F401", "F301"]
    assert out[0]["category"] == "territory_uae_illegal_acts"
    assert any("conflict" in n for n in notes)


def test_apply_plan_guards_against_hallucinated_ids_and_burying():
    from greenlight.agents.adjudicator import apply_plan

    flags = [make_flag("F101", "BLOCKER")]
    plan = {
        "merges": [
            {
                "surviving_flag_id": "F999",  # unknown: ignored
                "merged_flag_ids": ["F101"],
                "category": "x",
                "severity": "FYI",
                "rationale": "",
            },
            {
                "surviving_flag_id": "F101",
                "merged_flag_ids": [],
                "category": "sync_license",
                "severity": "FYI",  # 3-step downgrade: refused outright
                "rationale": "bury it",
            },
        ],
        "conflicts": [],
    }
    out, _ = apply_plan(flags, plan)
    assert len(out) == 1 and out[0]["flag_id"] == "F101"
    # A plan severity more than one step below the evidence is refused, not
    # clamped — a proposal that far off should not move severity at all.
    assert out[0]["severity"] == "BLOCKER"
    assert out[0]["category"] == "sync_license"


def test_dimension_scores_decompose_the_composite():
    from greenlight.report import dimension_scores

    flags = [
        make_flag("F101", "BLOCKER"),
        make_flag("F201", "HIGH", agent="ratings_board"),
    ]
    d = dimension_scores(flags)
    assert d["clearance_counsel"] == 70
    assert d["ratings_board"] == 92
    assert d["safety_underwriter"] == 100  # no flags = clean dimension
    rep = build_report("X", flags)
    assert rep["dimension_scores"] == d

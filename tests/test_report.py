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


def test_apply_verdicts_partial_marks_without_capping():
    """Severity is a risk judgment: the old MEDIUM cap parked blank-fire
    stunts below location fees because a citation carried a caveat."""
    kept, _ = apply_verdicts(
        [make_flag("F101", "BLOCKER")], {"F101": {"verdict": "PARTIAL", "reason": "narrower"}}
    )
    assert kept[0]["severity"] == "BLOCKER"
    assert kept[0]["finding"].startswith("[partially supported]")
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


def test_exact_duplicates_merge_deterministically():
    from greenlight.agents.adjudicator import merge_exact_duplicates

    a = make_flag("F401", "HIGH", agent="territory_censor")
    b = make_flag("F402", "BLOCKER", agent="territory_censor")  # same category, same scene
    c = make_flag("F301", "HIGH", agent="safety_underwriter")  # different desk survives
    merged = merge_exact_duplicates([a, b, c])
    assert len(merged) == 2
    keeper = next(f for f in merged if f["agent"] == "territory_censor")
    assert keeper["severity"] == "BLOCKER"  # higher severity wins the merge


def test_fail_open_flags_excluded_from_score():
    """A run with the verifier down must not score like a verified run."""
    from greenlight.report import greenlight_score

    verified = [{"severity": "HIGH", "remedy": {}}]
    unverified = [{"severity": "BLOCKER", "remedy": {}, "verification_unavailable": True}]
    assert greenlight_score(verified + unverified) == greenlight_score(verified)


# --- run-4 review batch: verifier window, two-path cost, plan hygiene --------


def test_apply_verdicts_misstatement_is_recoverable():
    """A rejection resting on a factual error must go around for correction,
    not delete the finding (run 4: the correction branch was dead code and
    every misstatement rejection was final)."""
    flags = [make_flag("F101", "HIGH")]
    _, rejected = apply_verdicts(
        flags,
        {
            "F101": {
                "verdict": "UNSUPPORTED",
                "reason": "misstates",
                "failure_mode": "script_misstatement",
            }
        },
    )
    assert rejected[0]["recoverable"] is True


def test_cost_paths_split_when_adjudication_moots_a_remedy():
    flags = [
        make_flag("F101", "HIGH", cost=[70000, 160000]),
        make_flag("F201", "MEDIUM", cost=[1000, 2000]),
    ]
    flags[0]["cost_excluded_on_target_path"] = True
    rep = build_report("X", flags, page_count=10)
    assert rep["est_clearance_cost_usd"] == [71000, 162000]
    assert rep["est_cost_paths"]["as_written"] == [71000, 162000]
    assert rep["est_cost_paths"]["target_rating"] == [1000, 2000]
    # no marker, no split key
    rep2 = build_report("X", [make_flag("F101", "HIGH", cost=[1, 2])], page_count=10)
    assert "est_cost_paths" not in rep2


def test_apply_plan_marks_target_path_moot_flags_and_formats_notes():
    from greenlight.agents.adjudicator import apply_plan

    flags = [make_flag("F101", "HIGH"), make_flag("F201", "MEDIUM")]
    plan = {
        "merges": [
            {
                "surviving_flag_id": "F101",
                "merged_flag_ids": [],
                "category": "sync_license",
                "severity": "HIGH",
                "rationale": "normalized slug",
            }
        ],
        "conflicts": [
            {
                "flag_ids": ["F101", "F201"],
                "resolution": "Cut the song for the rating; the license becomes moot.",
                "target_path_moot_flag_ids": ["F101"],
            }
        ],
    }
    out, notes = apply_plan(flags, plan)
    by_id = {f["flag_id"]: f for f in out}
    assert by_id["F101"].get("cost_excluded_on_target_path") is True
    assert "F201" not in {f["flag_id"] for f in out if f.get("cost_excluded_on_target_path")}
    # a rename note names the category; no "absorbed none" ever renders
    assert any("category normalized to sync_license" in n for n in notes)
    assert not any("absorbed none" in n for n in notes)


def test_merge_does_not_recap_partial_severity():
    """PARTIAL is a confidence marker, not a severity cap (run-3 decision) —
    a merge must not quietly restore the old MEDIUM cap."""
    from greenlight.agents.adjudicator import merge_exact_duplicates

    a = make_flag("F101", "HIGH")
    a["finding"] = "[partially supported] A finding."
    b = make_flag("F102", "HIGH")
    merged = merge_exact_duplicates([a, b])
    assert len(merged) == 1
    assert merged[0]["severity"] == "HIGH"


def test_blocker_may_drop_exactly_one_step_with_rationale():
    """Run 5: both blockers were secondary-market alt-cut items. The plan may
    correct BLOCKER -> HIGH with a stated rationale; never further."""
    from greenlight.agents.adjudicator import apply_plan

    flags = [make_flag("F101", "BLOCKER")]
    plan = {
        "merges": [
            {
                "surviving_flag_id": "F101",
                "merged_flag_ids": [],
                "category": "territory_cn_supernatural",
                "severity": "HIGH",
                "rationale": "CN alt-cut deliverable; stops nothing domestic",
            }
        ],
        "conflicts": [],
    }
    out, _ = apply_plan(flags, plan)
    assert out[0]["severity"] == "HIGH"
    # without a rationale the downgrade is refused
    plan["merges"][0]["rationale"] = ""
    out2, _ = apply_plan([make_flag("F101", "BLOCKER")], plan)
    assert out2[0]["severity"] == "BLOCKER"


def test_failed_verifier_withholds_the_score_instead_of_inflating_it():
    """A Vertex outage fails every verification OPEN. _scored() drops those
    flags from the maths, so the score used to come out 100/100 while the
    counts beside it still listed the blockers."""
    flags = [
        {**make_flag("F101", "BLOCKER"), "verification_unavailable": True},
        {**make_flag("F102", "HIGH"), "verification_unavailable": True},
    ]
    rep = build_report("X", flags, page_count=10)
    assert rep["greenlight_score"] is None, "unverified must never score like verified"
    assert rep["dimension_scores"] == {}
    assert rep["verification_degraded"] is True
    assert rep["counts"]["BLOCKER"] == 1  # the findings still render
    # a fully verified run is unaffected
    clean = build_report("X", [make_flag("F101", "HIGH")], page_count=10)
    assert clean["greenlight_score"] == 92 and clean["verification_degraded"] is False


# --- B5 / B13: verification must not misreport its own output ---------------


def test_missing_verdicts_alone_do_not_mark_flags():
    """Pins the underlying behaviour the salvage fix compensates for."""
    from greenlight.agents.verification import apply_verdicts

    kept, rejected = apply_verdicts([make_flag("F101", "HIGH")], {})
    assert kept and not rejected
    assert "verification_unavailable" not in kept[0], "unmarked is the trap"


def test_failopen_verdicts_mark_every_flag_and_withhold_the_score():
    from greenlight.agents.verification import apply_verdicts

    flags = [make_flag("F101", "BLOCKER"), make_flag("F102", "HIGH")]
    failopen = {
        f["flag_id"]: {"verdict": "SUPPORTED", "reason": "unavailable", "fail_open": True}
        for f in flags
    }
    kept, _ = apply_verdicts(flags, failopen)
    assert all(f["verification_unavailable"] for f in kept)
    rep = build_report("X", kept, page_count=10)
    assert rep["greenlight_score"] is None and rep["verification_degraded"] is True


def test_sourcing_failure_rejections_become_open_questions():
    """Shared by the panel and the salvage path: a claim the verifier could not
    SOURCE is not a claim it disproved, so its scenes must not read clean."""
    from greenlight.agents.verification import demotion_entries

    dropped = [
        {
            "flag_id": "F302",
            "agent": "safety_underwriter",
            "scene_ids": ["S074", "S080"],
            "finding": "110mph in a convertible missing its passenger door.",
            "failure_mode": "premise_unsupported",
        },
        {"flag_id": "F109", "agent": "clearance_counsel", "failure_mode": "script_misstatement"},
    ]
    out = demotion_entries(dropped)
    assert list(out) == ["open_questions:safety_underwriter"], "only sourcing failures demote"
    entry = out["open_questions:safety_underwriter"][0]
    assert "F302" in entry and "S074, S080" in entry and "not" in entry


def test_adjudication_plan_applies_before_code_dedupe():
    """Reversed, merge_exact_duplicates absorbed the flag the plan named as
    SURVIVOR; apply_plan ignores unknown ids, so the merge, the category
    normalization and the rationale were all silently lost."""
    from greenlight.agents.adjudicator import apply_plan, merge_exact_duplicates

    a = make_flag("F1001", "MEDIUM")
    b = make_flag("F1002", "HIGH")
    for f in (a, b):
        f["category"] = "music"  # same desk + category + scenes -> code dedupe pair
    plan = {
        "merges": [
            {
                "surviving_flag_id": "F1002",
                "merged_flag_ids": ["F1001"],
                "category": "sync_license",
                "severity": "HIGH",
                "rationale": "one licence, filed twice",
            }
        ],
        "conflicts": [],
    }
    # plan first, then dedupe — the order pipeline now uses
    out, notes = apply_plan([a, b], plan)
    out = merge_exact_duplicates(out)
    assert [f["flag_id"] for f in out] == ["F1002"]
    assert out[0]["category"] == "sync_license", "the plan's normalization survived"
    assert any("absorbed F1001" in n for n in notes)


# --- run-7 review: binder self-consistency ----------------------------------


def test_prose_named_scene_is_not_marked_no_known_issue():
    """A scene a finding NAMES in its body must not also render 'No known issue'
    (F3006 called S069 a heat scene while S069 got its own clean row)."""
    from greenlight import binder

    record = {
        "flags": [
            {
                "flag_id": "F3006",
                "agent": "safety_underwriter",
                "scene_ids": ["S003", "S064"],
                "citations": [{"excerpt": "x"}],
                "severity": "MEDIUM",
                "category": "weather_exposure",
                "finding": "Desert heat exposure across S003, S064 and S069.",
                "remedy": {"action": "ADD_SPECIALIST", "detail": "medic on set"},
                "confidence": 0.9,
            }
        ],
        "rejected_flags": [],
        "open_questions": {},
        "report": {},
    }
    scene_meta = {
        f"S{i:03d}": {"heading": f"EXT. SCENE {i}", "page": i, "number": str(i)}
        for i in (3, 64, 69)
    }
    data = binder.build(record, scene_meta)
    rows_by_scene = {r["Scene"]: r for r in data["rows"]}
    s069 = rows_by_scene.get("Sc. 69")
    # the prose reference makes S069 "touched", so it folds into the finding
    # that names it and never emits a standalone "No known issue" row
    assert s069 is None or s069["Clearance status"] != "No known issue"


def test_argued_scene_is_deterministic_by_scene_order():
    from greenlight.binder import _argued_scene

    f = {"finding": "argues from S046 and also S012", "remedy": {}}
    # both named; the LOWEST by scene order wins regardless of prose order
    assert _argued_scene(f, ["S012", "S046"]) == "S012"


# --- run-8: adjudication integrity + prose/coordinate reconciliation --------


def test_no_action_finding_is_not_absorbed_by_dedupe():
    """An R-driver violence finding must not be swallowed by a same-category
    'No Action' finding — that cleared the exploding-lip scene (run-8 F2008)."""
    from greenlight.agents.adjudicator import merge_exact_duplicates

    no_action = {
        **make_flag("F2007", "MEDIUM"),
        "category": "rating_violence",
        "remedy": {"action": "NO_ACTION", "detail": "fine as written"},
    }
    actionable = {
        **make_flag("F2008", "HIGH"),
        "category": "rating_violence",
        "scene_ids": ["S064"],
        "remedy": {"action": "CUT", "detail": "trim the gore"},
    }
    out = merge_exact_duplicates([no_action, actionable])
    assert {f["flag_id"] for f in out} == {"F2007", "F2008"}
    # two findings that SHARE a disposition still consolidate
    dup = {**actionable, "flag_id": "F2010", "scene_ids": ["S066"]}
    two_actionable = merge_exact_duplicates([actionable, dup])
    assert len(two_actionable) == 1


def test_apply_plan_does_not_claim_a_severity_change_it_refused():
    """The note said 'F2008: severity upgraded from MEDIUM' while apply_plan's
    own rule refused the MEDIUM->HIGH upgrade — a claimed change that never
    happened."""
    from greenlight.agents.adjudicator import apply_plan

    flags = [make_flag("F2008", "MEDIUM")]
    plan = {
        "merges": [
            {
                "surviving_flag_id": "F2008",
                "merged_flag_ids": [],
                "category": "rating_violence",
                "severity": "HIGH",
                "rationale": "R",
            }
        ],
        "conflicts": [],
    }
    out, notes = apply_plan(flags, plan)
    assert out[0]["severity"] == "MEDIUM", "upgrade must still be refused"
    assert not any("upgrad" in n.lower() for n in notes), "no note may claim the refused upgrade"

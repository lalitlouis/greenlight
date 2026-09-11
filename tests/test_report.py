"""Deterministic report assembly and verdict application. No API calls."""

import pytest

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
    assert not kept[0].get("verification_unavailable")
    assert kept[1]["verification_unavailable"] is True
    assert "verification_unavailable" not in flags[1]  # do not mutate filed evidence
    assert build_report("X", kept)["greenlight_score"] is None


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


@pytest.mark.parametrize(
    "verdict",
    [None, {}, {"verdict": "SUPPORTED"}, {"verdict": "UNKNOWN", "reason": "bad output"}],
)
def test_missing_or_invalid_verdict_withholds_score_and_estimates(verdict):
    """Missing evidence must not certify a report or contribute verified costs."""
    flag = make_flag("F101", "HIGH", cost=[1000, 5000], days=10)
    kept, rejected = apply_verdicts([flag], {"F101": verdict})
    assert kept and not rejected
    assert kept[0]["verification_unavailable"] is True
    report = build_report("X", kept)
    assert report["greenlight_score"] is None
    assert report["dimension_scores"] == {}
    assert report["verification_degraded"] is True
    assert report["est_clearance_cost_usd"] is None
    assert report["est_added_days"] is None
    assert report["counts"]["HIGH"] == 1


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


def test_cleared_row_citing_a_kept_finding_moves_to_the_note():
    """A disposition receipt like 'dispositioned in F2001' is a cross-reference,
    not a clearance — it must not print under 'no action needed' (THE NIGHT
    COUNTER profanity row, 2026-09-01)."""
    from greenlight import binder

    record = {
        "flags": [
            {"flag_id": "F2001", "agent": "ratings_board", "entity_id": "e-lang", "citations": []}
        ],
        "entities": [{"entity_id": "e-prof", "surface": "Profanity"}],
        "cleared": {
            "ratings_board": [
                {
                    "entity_id": "e-prof",
                    "reasoning": "Profanity evaluated and formally dispositioned "
                    "in language census finding F2001.",
                },
                {"entity_id": "e-prof2", "reasoning": "No known issue for this mention."},
            ]
        },
        "open_questions": {},
        "report": {},
    }
    bm = binder._back_matter(record)
    texts = [c["text"] for c in bm["cleared"]]
    assert not any("F2001" in t for t in texts if "further determination" not in t)
    assert any("further determination" in t for t in texts)


# ---- review 2026-09-01 (Worker 4A): assembly integrity pass -----------------


def _rec_for_finalize():
    f1 = make_flag("F4003", "HIGH", agent="territory_censor")
    f1["category"] = "territory_cn_drug_use"
    f1["entity_id"] = "E001"
    f1["scene_ids"] = ["S003"]
    f1["finding"] = "Cannabis in S003; see also F4004 for the UAE angle."
    f2 = make_flag("F1009", "HIGH")
    f2["category"] = "sync_license"
    f2["entity_id"] = "E009"
    f2["scene_ids"] = ["S004"]
    return {
        "flags": [f1, f2],
        "report": {"flags": [f1, f2]},
        "rejected_flags": [dict(make_flag("F4008", "HIGH"), rejection_reason="x")],
        "withdrawn_flag_ids": ["F2003"],
        "absorbed_into": {"F4004": "F4003"},
        "scene_meta": {"S003": {"heading": "EXT. PIER"}, "S004": {"heading": "INT. CHURCH"}},
        "entities": [
            {"entity_id": "E001", "surface": "cannabis joint"},
            {"entity_id": "E009", "surface": "Hallelujah"},
        ],
        "entity_accounting": {"fold": {}, "fragment_ids": [], "body_flagged_ids": []},
        "cleared": {
            "territory_censor": [
                {"entity_id": "", "reasoning": "Drug use addressed under F4003 and F4004."},
                {"entity_id": "", "reasoning": "Cleared; the alt-cut point sits in F4008."},
            ],
            "completeness_sweep": [
                {"entity_id": "E050", "reasoning": "Swept; language handled in F2003."}
            ],
        },
        "adjudication_notes": ["F4004: absorbed F4009 (dup)", "conflict: F4003 vs F1009 remedies"],
        "open_questions": {
            "clearance_counsel": [
                "Confirm whether Sony controls 100% of Hallelujah sync rights.",
                "Unresolved — the artwork finding (F1006, S002) was filed but its citation "
                "support did not hold.",
                "Is the Boston Whaler logo visible?",
            ],
            "territory_censor": ["Does F4003's alt cut satisfy UAE exhibitors?"],
        },
    }


def test_finalize_rewrites_absorbed_ids_and_annotates_rejected_and_withdrawn():
    from greenlight.pipeline import finalize_record_after_verification

    rec = _rec_for_finalize()
    manifest = finalize_record_after_verification(rec)
    tc = rec["cleared"]["territory_censor"]
    # absorbed id -> survivor, and the duplicated reference collapses to one
    assert tc[0]["reasoning"] == "Drug use addressed under F4003."
    # rejected id annotated (every bucket, sweep included)
    assert "F4008 (later rejected in verification — see Rejected)" in tc[1]["reasoning"]
    sweep = rec["cleared"]["completeness_sweep"][0]["reasoning"]
    assert "F2003 (withdrawn — see Open questions)" in sweep
    # finding text rewritten too, and the report's flag list shares the objects
    assert "F4004" not in rec["flags"][0]["finding"]
    assert rec["report"]["flags"][0]["finding"] == rec["flags"][0]["finding"]
    # annotation is idempotent
    finalize_record_after_verification(rec)
    assert tc[1]["reasoning"].count("later rejected") == 1
    # dangling adjudication note dropped AFTER the rewrite (F4009 never rendered)
    assert rec["adjudication_notes"] == ["conflict: F4003 vs F1009 remedies"]
    assert not [m for m in manifest if m["guard"] == "prose_scene_missing"]


def test_finalize_routes_open_questions_to_their_findings():
    from greenlight.pipeline import finalize_record_after_verification

    rec = _rec_for_finalize()
    finalize_record_after_verification(rec)
    # names the flagged entity's surface (same desk) -> follow-up on F1009
    assert rec["oq_followups"]["F1009"] == [
        "Confirm whether Sony controls 100% of Hallelujah sync rights."
    ]
    # names a rendered same-desk id -> follow-up on F4003
    assert rec["oq_followups"]["F4003"] == ["Does F4003's alt cut satisfy UAE exhibitors?"]
    # the Unresolved template and unrelated questions stay
    cc = rec["open_questions"]["clearance_counsel"]
    assert len(cc) == 2 and cc[0].startswith("Unresolved —") and "Boston Whaler" in cc[1]
    assert rec["open_questions"]["territory_censor"] == []
    # the header decomposition is on the record
    assert rec["entity_accounting"]["items_examined"] == {
        "entity_rows": 0,
        "script_level": 2,  # the annotated 'Cleared; ... F4008' row + the sweep row
        "flagged_elsewhere": 1,  # the row citing rendered F4003
    }


def test_finalize_records_prose_naming_a_phantom_scene():
    from greenlight.pipeline import finalize_record_after_verification

    rec = _rec_for_finalize()
    rec["flags"][1]["finding"] = "Hallelujah plays in S004 and S049."
    manifest = finalize_record_after_verification(rec)
    hits = [m for m in manifest if m["guard"] == "prose_scene_missing"]
    assert hits == [
        {
            "guard": "prose_scene_missing",
            "stage": "assembly",
            "flag_id": "F1009",
            "scene_ids": ["S049"],
        }
    ]


def test_absorption_map_covers_plan_and_code_dedupe_with_chains():
    from greenlight.pipeline import _absorption_map

    a = make_flag("F101", "HIGH")
    b = make_flag("F102", "MEDIUM")  # plan merges b into a
    c = make_flag("F103", "MEDIUM")  # code dedupe: same desk/category/scene as a
    d = make_flag("F104", "LOW")  # rating: script-wide, disjoint scenes
    e = make_flag("F105", "LOW", agent="ratings_board")
    for f in (a, b, c):
        f["category"] = "trademark_use"
    d["category"] = e["category"] = "rating_language"
    d["agent"] = "ratings_board"
    d["scene_ids"] = ["S009"]
    plan = {"merges": [{"surviving_flag_id": "F101", "merged_flag_ids": ["F102"]}]}
    out = _absorption_map([a, b, c, d, e], [a, e], plan)
    assert out == {"F102": "F101", "F103": "F101", "F104": "F105"}
    # chain: plan says F102 -> F101, but F101 itself was deduped into F100
    z = dict(make_flag("F100", "HIGH"), category="trademark_use")
    out2 = _absorption_map([z, a, b], [z], plan)
    assert out2 == {"F101": "F100", "F102": "F100"}


def test_cost_paths_excluded_built_from_scored_and_days_split():
    from greenlight.report import _added_days, _cost_paths

    kept = make_flag("F1", "HIGH", cost=[100, 200], days=3)
    moot = make_flag("F2", "MEDIUM", cost=[50, 60], days=9)
    moot["cost_excluded_on_target_path"] = True
    failopen = make_flag("F3", "MEDIUM", cost=[1000, 2000], days=30)
    failopen["cost_excluded_on_target_path"] = True
    failopen["verification_unavailable"] = True
    paths = _cost_paths([kept, moot, failopen])
    # the fail-open flag is outside every total, so also outside the delta
    assert [e["flag_id"] for e in paths["excluded"]] == ["F2"]
    lo = sum(e["est_cost_usd"][0] for e in paths["excluded"])
    hi = sum(e["est_cost_usd"][1] for e in paths["excluded"])
    assert [
        paths["as_written"][0] - paths["target_rating"][0],
        paths["as_written"][1] - paths["target_rating"][1],
    ] == [lo, hi]
    assert paths["as_written_days"] == 9 and paths["target_rating_days"] == 3
    assert _added_days([kept, moot, failopen]) == 9


def test_internal_ids_are_stripped_from_reader_facing_text():
    from greenlight.pipeline import _strip_internal_ids as strip

    assert strip("For E030 (CC-W030, Limp Bizkit cue in S032), the script specifies no title.") == (
        "Limp Bizkit cue in S032: the script specifies no title."
    )
    assert strip("E050 (Mozart in S084): While the compositions are public domain.") == (
        "Mozart in S084: While the compositions are public domain."
    )
    assert strip("For SU-W008 (mechanical bull sequence in S055), it remains open.") == (
        "Mechanical bull sequence in S055: it remains open."
    )
    assert strip("Sweep credited SW-RB-E014 for the hymn in S004 under F2001.") == (
        "Sweep credited for the hymn in S004 under F2001."
    )
    assert strip("Nothing internal here (S003, F1001).") == "Nothing internal here (S003, F1001)."

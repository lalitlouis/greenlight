"""Regression set for assertion-1 overturn guards (review 2026-09-01, A1).

Three production records shipped false overturns: an off-topic-citation
rejection flipped to SUPPORTED because a newspaper's own name co-occurred in
one scene (F1004), a correct script_misstatement flipped because a supporting
quote sat beside a genuinely absent token (Reservoir Dogs F2004), and a
"GROUND PARTIALLY OVERTURNED" note was written onto a rejection that raised no
unstated-fact objection (Little Miss Sunshine F1005). Each case is pinned here
beside one positive control per path, so the guards stay precise AND alive.
"""

from __future__ import annotations

from greenlight.agents.verification import (
    _apply_overturns,
    _cut_list_at_target,
    _overturned_by_script,
    _refile_gate_problem,
    _stated_fact_overturn,
)


def _wheelhouse_state():
    s001 = "EXT. PORT BANNOCK HARBOR - DAWN\n\nGulls. A skiff idles.\n"
    s002 = (
        "\fINT. THE WHEELHOUSE - DAY\n\nBeside it, framed: a front page of the Gloucester "
        'Daily Times -- "BANNOCK CAPTAIN PULLS FOUR FROM NOR\'EASTER."\n\nSAM (10) sits at '
        "the end of the bar doing serious damage to a cocoa.\n"
    )
    text = s001 + s002
    return {
        "script_text": text,
        "scenes": [
            {"scene_id": "S001", "raw_span": [0, len(s001)], "heading": "EXT. HARBOR"},
            {"scene_id": "S002", "raw_span": [len(s001), len(text)], "heading": "INT. WHEELHOUSE"},
        ],
    }


F1004_REASON = (
    "The scene text accurately shows a framed front page of the Gloucester Daily Times "
    "with the quoted headline, but the cited excerpt—an interview with a prop designer "
    "discussing how they design fictional newspapers—does not support the legal premise "
    "that reproducing a real masthead requires publication clearance."
)


def test_f1004_offtopic_citation_rejection_is_never_flipped():
    """No claimed number → no stated-fact anchor; and a citation_offtopic verdict
    can at most lose a ground, never become SUPPORTED."""
    state = _wheelhouse_state()
    assert _stated_fact_overturn(F1004_REASON, state) is None
    flags = [{"flag_id": "F1004", "scene_ids": ["S002"], "category": "publication_clearance"}]
    verdicts = {
        "F1004": {
            "verdict": "UNSUPPORTED",
            "reason": F1004_REASON,
            "failure_mode": "citation_offtopic",
        }
    }
    out = _apply_overturns(flags, verdicts, state)
    assert out == []
    assert verdicts["F1004"]["verdict"] == "UNSUPPORTED"
    assert verdicts["F1004"]["failure_mode"] == "citation_offtopic"


def test_sourcing_failure_mode_blocks_a_full_flip_even_with_a_stated_fact():
    """Ages ARE stated in S002 — the false ground is struck — but a verdict the
    verifier filed as premise_unsupported keeps its rejection."""
    state = _wheelhouse_state()
    reason = "The claim assumes Sam is 10 (unstated); Sam and Cocoa appear briefly."
    flags = [
        {
            "flag_id": "F3008",
            "scene_ids": ["S009"],
            "category": "minor_safety",
            "finding": "Sam (10) and the dog Cocoa ride the skiff at night.",
        }
    ]
    verdicts = {
        "F3008": {"verdict": "UNSUPPORTED", "reason": reason, "failure_mode": "premise_unsupported"}
    }
    _apply_overturns(flags, verdicts, state)
    v = verdicts["F3008"]
    assert v["verdict"] == "UNSUPPORTED"
    assert v["failure_mode"] == "premise_unsupported"
    assert v.get("ground_overturned") is True or "OVERTURNED" not in v["reason"]


def _dogs_state():
    text = "INT. WAREHOUSE - DAY\n\nMr. Blonde LIGHTS up a match and dances toward the cop.\n"
    return {
        "script_text": text,
        "scenes": [{"scene_id": "S021", "raw_span": [0, len(text)], "heading": "INT. WAREHOUSE"}],
    }


RD_F2004_REASON = (
    "The claim misstates the script facts: in S021, Mr. Blonde lights a match "
    "('Mr. Blonde LIGHTS up a match'), not a Zippo lighter ('zippo' is a concrete noun "
    "found nowhere in the screenplay)."
)


def test_reservoir_dogs_f2004_supporting_quote_beside_absent_token_does_not_flip():
    """The absence is asserted about 'zippo' (genuinely absent); the quote that
    exists is the verifier's SUPPORTING evidence. A correct script_misstatement
    must stand."""
    state = _dogs_state()
    assert _overturned_by_script(RD_F2004_REASON, state) is None
    flags = [{"flag_id": "F2004", "scene_ids": ["S021"], "category": "rating_smoking"}]
    verdicts = {
        "F2004": {
            "verdict": "UNSUPPORTED",
            "reason": RD_F2004_REASON,
            "failure_mode": "script_misstatement",
        }
    }
    assert _apply_overturns(flags, verdicts, state) == []
    assert verdicts["F2004"]["verdict"] == "UNSUPPORTED"


def test_absence_overturn_positive_control_still_fires_and_keeps_full_reason():
    state = _dogs_state()
    reason = "The line 'Mr. Blonde LIGHTS up a match' does not appear anywhere in the screenplay."
    assert _overturned_by_script(reason, state) == ("Mr. Blonde LIGHTS up a match", "S021")
    flags = [{"flag_id": "F2004", "scene_ids": ["S021"]}]
    verdicts = {"F2004": {"verdict": "UNSUPPORTED", "reason": reason * 3}}
    out = _apply_overturns(flags, verdicts, state)
    assert out and out[0][2] == "S021"
    assert verdicts["F2004"]["verdict"] == "SUPPORTED"
    # the original rejection is kept WHOLE on the record (was truncated to 200 chars)
    assert verdicts["F2004"]["reason"].endswith(reason * 3)


def test_absence_about_an_excerpt_is_not_a_script_absence():
    state = _dogs_state()
    reason = (
        "The cited excerpt does not contain 'Mr. Blonde LIGHTS up a match' or any "
        "discussion of on-screen smoking."
    )
    assert _overturned_by_script(reason, state) is None


def _sunshine_state():
    text = (
        "INT. HOLIDAY INN LOBBY - BOCA RATON - DAY\n\nThe Hoovers check in. A pageant "
        "banner hangs over the desk.\n"
    )
    return {
        "script_text": text,
        "scenes": [{"scene_id": "S088", "raw_span": [0, len(text)], "heading": "INT. HOLIDAY INN"}],
    }


LMS_F1005_REASON = (
    "While the script explicitly places the pageant and hotel scenes at a Holiday Inn in "
    "Boca Raton, the cited excerpt is an off-topic legal snippet about a holdover "
    "franchisee dispute that does not establish that filming at a franchised hotel "
    "requires a location agreement with the franchisor."
)


def test_little_miss_sunshine_f1005_no_false_ground_struck_note():
    """No unstated-fact objection was raised and no number was claimed: the verdict
    must pass through untouched — no 'GROUND PARTIALLY OVERTURNED' prose."""
    state = _sunshine_state()
    flags = [{"flag_id": "F1005", "scene_ids": ["S088"], "category": "location_release"}]
    original = {
        "verdict": "UNSUPPORTED",
        "reason": LMS_F1005_REASON,
        "failure_mode": "citation_offtopic",
    }
    verdicts = {"F1005": dict(original)}
    assert _apply_overturns(flags, verdicts, state) == []
    assert verdicts["F1005"] == original


def _daughters_state():
    s004 = "INT. BAR - DAY\n\nSTU\nHaylee is two, and Kaitlin is already four! Believe it?!\n"
    s084 = "\f\nEXT. CHAPEL - DAY\n\nStu weds; Haylee and Kaitlin scatter petals.\n"
    text = s004 + s084
    return {
        "script_text": text,
        "scenes": [
            {"scene_id": "S004", "raw_span": [0, len(s004)], "heading": "INT. BAR - DAY"},
            {"scene_id": "S084", "raw_span": [len(s004), len(text)], "heading": "EXT. CHAPEL"},
        ],
    }


def test_stated_fact_positive_control_still_fires_on_a_pure_unstated_ground():
    state = _daughters_state()
    reason = (
        "The scene text in S084 does not specify the ages of Stu's daughters "
        "(Haylee and Kaitlin as age 2 and age 4), assuming unstated facts."
    )
    flags = [{"flag_id": "F3011", "scene_ids": ["S084"], "category": "minor_safety"}]
    verdicts = {"F3011": {"verdict": "UNSUPPORTED", "reason": reason}}
    _apply_overturns(flags, verdicts, state)
    assert verdicts["F3011"]["verdict"] == "SUPPORTED"
    assert flags[0]["scene_ids"] == ["S004", "S084"]


def test_stated_fact_requires_a_claimed_number_no_proper_noun_fallback():
    state = _daughters_state()
    # names co-occur in S004 but nothing numeric is claimed: no anchor, no flip
    assert (
        _stated_fact_overturn("Unstated: Haylee and Kaitlin's relationship to Stu.", state) is None
    )


# ---- re-source / refile gates (A5) ------------------------------------------


def test_refile_gate_high_needs_authority_or_two_hosts_after_resource():
    flag = {
        "category": "location_release",
        "severity": "HIGH",
        "finding": "Filming at the venue requires a location agreement.",
        "remedy": {"detail": "Negotiate a location agreement."},
        "citations": [
            {"url": "https://someblog.example.com/post", "excerpt": "You need an agreement."}
        ],
    }
    problem = _refile_gate_problem(flag, check_authority=True)
    assert problem and problem.startswith("re-source gate (authority tier)")
    # two independent non-background hosts corroborate a HIGH
    flag["citations"].append(
        {
            "url": "https://otherhost.example.org/guide",
            "excerpt": "Location agreements are standard.",
        }
    )
    assert _refile_gate_problem(flag, check_authority=True) is None


def test_refile_gate_statute_section_must_trace_to_own_excerpts():
    flag = {
        "category": "government_insignia",
        "severity": "MEDIUM",
        "finding": "Under 14 U.S.C. § 933 the Coast Guard ensign is restricted.",
        "remedy": {"detail": "Replace the markings."},
        "citations": [{"url": "https://www.uscg.mil/x", "excerpt": "The emblem is protected."}],
    }
    problem = _refile_gate_problem(flag, check_authority=True)
    assert problem and "933" in problem and "statute traceability" in problem
    flag["citations"].append(
        {"url": None, "via": "local", "source_type": "statute", "excerpt": "14 USC 933 - ensigns"}
    )
    assert _refile_gate_problem(flag, check_authority=True) is None


def test_refile_gate_blocks_relaundered_rule_and_bundled_master():
    rating = {
        "category": "rating_language",
        "severity": "MEDIUM",
        "finding": "Two F-words require an R rating.",
        "remedy": {"detail": "Cut one."},
        "citations": [{"url": None, "via": "local", "excerpt": "'language': R 79% ..."}],
    }
    assert "normative rule" in (_refile_gate_problem(rating, check_authority=False) or "")
    sync = {
        "category": "sync_license",
        "severity": "HIGH",
        "finding": "The composition needs a sync license and the recording a master use license.",
        "remedy": {"detail": "License both."},
        "citations": [{"url": "https://www.ascap.com/x", "excerpt": "Sync licensing ..."}],
    }
    assert "sync/master" in (_refile_gate_problem(sync, check_authority=False) or "")


def test_cut_list_at_target_rank_rule():
    assert _cut_list_at_target({"predicted": "R", "target": "R"})
    assert _cut_list_at_target({"predicted": "PG-13", "target": "R"})
    assert not _cut_list_at_target({"predicted": "R", "target": "PG-13"})
    assert not _cut_list_at_target({"predicted": "R", "target": None})

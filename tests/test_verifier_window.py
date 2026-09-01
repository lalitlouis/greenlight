"""The verifier's evidence window. Run 4: four of five rejections were false,
every one an absence ruling made from a partial window ("neither line appears
in dialogue" — both lines sat in a scene the finding never named). The
mechanical full-script search is the fix; these tests pin it."""

from greenlight.agents.verification import _scene_context, _search_context


def _state():
    text = (
        "INT. MALL - DAY\n\nSTEVE\nSbarro, over in the Fremont mall.\n\n"
        "ALAN (V.O.)\nI paid 7 grand for Sbarro?!\n\n"
        "INT. HOUSE - DAY\n\nTRACY\nHaylee is two, and Kaitlin is already four!\n"
    )
    split = text.index("INT. HOUSE")
    return {
        "script_text": text,
        "scenes": [
            {"scene_id": "S023", "raw_span": [0, split], "heading": "INT. MALL - DAY"},
            {"scene_id": "S004", "raw_span": [split, len(text)], "heading": "INT. HOUSE - DAY"},
        ],
    }


def _flag(finding, detail="Do the thing.", scene_ids=None):
    return {
        "flag_id": "F109",
        "scene_ids": scene_ids or ["S023"],
        "finding": finding,
        "remedy": {"action": "REPLACE", "detail": detail},
        "citations": [],
        "severity": "MEDIUM",
        "category": "test",
    }


def test_search_finds_quoted_string_in_uncited_scene():
    out = _search_context(_flag('The line "I paid 7 grand for Sbarro?!" is spoken.'), _state())
    assert "FOUND in S023" in out


def test_search_reports_not_found_honestly():
    out = _search_context(_flag('The script says "Jägermeister toast at dawn" happens.'), _state())
    assert "NOT FOUND anywhere" in out


def test_search_survives_line_wrapped_quotes():
    # findings quote dialogue as one line; scripts wrap it
    state = _state()
    state["script_text"] = state["script_text"].replace("for Sbarro?!", "for\nSbarro?!")
    out = _search_context(_flag('Alan says "I paid 7 grand for Sbarro?!" on screen.'), state)
    assert "FOUND in S023" in out


def test_search_covers_remedy_quotes_and_handles_no_quotes():
    flag = _flag("No quotes here.", detail='Cut "Haylee is two" entirely.')
    out = _search_context(flag, _state())
    assert "FOUND in S004" in out
    # no quoted strings -> the absent-terms probe still reports claim words
    # found nowhere in the script (the contamination check's raw material)
    out2 = _search_context(_flag("Nothing quoted."), _state())
    assert "FOUND NOWHERE" in out2 and "nothing" in out2


def test_absent_terms_catch_released_film_contamination():
    """Run 5 (F107): 'live animals (rooster and tiger)... a baby left
    unattended' — the tiger and the baby are in the 2009 FILM, not this draft.
    The mechanical probe must surface them; words that ARE on the page must
    not appear."""
    from greenlight.agents.verification import _absent_terms

    script = "int. courtyard - day\na chicken struts past the overturned chair.\n"
    claim = "Live animals (rooster and tiger) roam; a baby left unattended near the chicken."
    absent = _absent_terms(claim, script)
    assert "tiger" in absent and "rooster" in absent and "baby" in absent
    assert "chicken" not in absent


def test_scene_context_includes_scenes_named_in_remedy():
    flag = _flag("A finding about the mall.", detail="Trim the S004 age line too.")
    out = _scene_context(flag, _state())
    assert "=== S004 ===" in out and "=== S023 ===" in out


# --- run-6 harness: assertion 1, normalization, stems ------------------------


def test_canon_matches_across_quote_and_dash_variants():
    """The real script uses curly apostrophes and em-dashes; findings quote in
    straight ASCII. Run 6's Sbarro rejection survived because the matcher
    treated the curly and straight apostrophe forms as different strings."""
    from greenlight.agents.verification import _find_in_script

    script = "STU\nIt\u2019s cool \u2014 I paid 7 grand for Sbarro?!\n"
    assert _find_in_script("It's cool - I paid 7 grand for Sbarro?!", script) >= 0
    assert _find_in_script("paid 7\ngrand for Sbarro", script) >= 0  # line wrap
    assert _find_in_script("PISTOL WHIPS", "He PISTOL-WHIPS Vick") >= 0  # hyphen joins


def test_quoted_spans_extract_single_quotes_without_apostrophe_traps():
    from greenlight.agents.verification import _quoted_spans

    text = (
        "The line 'I paid 7 grand for Sbarro?!' does not appear; "
        "Vick's car and Stu's ring aren't quotes; \"put away your sack\" is."
    )
    spans = _quoted_spans(text)
    assert "I paid 7 grand for Sbarro?!" in spans
    assert "put away your sack" in spans
    assert not any("Vick" in s and "Stu" in s for s in spans)  # apostrophes never pair


def _overturn_state():
    text = (
        "INT. MALL - DAY\n\nSTEVE\nSbarro, over in the Fremont mall.\n\n"
        "ALAN (V.O.)\nI paid 7 grand for Sbarro?!\n"
    )
    return {
        "script_text": text,
        "scenes": [{"scene_id": "S023", "raw_span": [0, len(text)], "heading": "INT. MALL"}],
    }


def test_assertion_overturns_false_absence_rejection():
    from greenlight.agents.verification import _overturned_by_script

    hit = _overturned_by_script(
        "The line 'I paid 7 grand for Sbarro?!' does not appear in the screenplay.",
        _overturn_state(),
    )
    assert hit == ("I paid 7 grand for Sbarro?!", "S023")


def test_assertion_leaves_supporting_quotes_and_true_absences_alone():
    from greenlight.agents.verification import _overturned_by_script

    state = _overturn_state()
    # quote used as supporting evidence for the rejection: stands
    supporting = (
        "The claim misstates the script: the page reads 'I paid 7 grand for Sbarro?!', "
        "which is comedic exaggeration, so the asserted liability is wrong."
    )
    assert _overturned_by_script(supporting, state) is None
    # quote genuinely absent: stands
    absent = "The line 'a tiger prowls the suite' does not appear in the screenplay."
    assert _overturned_by_script(absent, state) is None


def test_apply_overturns_flips_only_the_contradicted_verdict():
    from greenlight.agents.verification import _apply_overturns

    flags = [
        {"flag_id": "F112"},
        {"flag_id": "F116"},
    ]
    verdicts = {
        "F112": {
            "verdict": "UNSUPPORTED",
            "reason": "The line 'I paid 7 grand for Sbarro?!' does not appear in the screenplay.",
            "failure_mode": "script_misstatement",
        },
        "F116": {
            "verdict": "UNSUPPORTED",
            "reason": "The line 'Ride of the Valkyries plays' does not appear in the screenplay.",
            "failure_mode": "script_misstatement",
        },
    }
    out = _apply_overturns(flags, verdicts, _overturn_state())
    assert [(o[0], o[2]) for o in out] == [("F112", "S023")]
    assert verdicts["F112"]["verdict"] == "SUPPORTED" and verdicts["F112"]["overridden"]
    assert verdicts["F116"]["verdict"] == "UNSUPPORTED"  # genuinely absent: stands


def _daughters_state():
    # the fact (ages) is stated in S004; the finding argued from S084, which names
    # the daughters but not their ages — the F3011 partial-window rejection.
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


def test_unstated_fact_overturn_finds_stated_fact_and_widens_coordinates():
    from greenlight.agents.verification import _apply_overturns, _stated_fact_overturn

    state = _daughters_state()
    reason = (
        "The scene text in S084 does not specify the ages of Stu's daughters "
        "(Haylee and Kaitlin as age 2 and age 4), assuming unstated facts."
    )
    # names anchored to the claimed numbers — Stu (outside the window) is noise
    assert _stated_fact_overturn(reason, state) == ("Haylee, Kaitlin", "S004")
    flags = [{"flag_id": "F3011", "scene_ids": ["S084"], "category": "minor_safety"}]
    verdicts = {"F3011": {"verdict": "UNSUPPORTED", "reason": reason}}
    _apply_overturns(flags, verdicts, state)
    assert verdicts["F3011"]["verdict"] == "SUPPORTED"  # pure unstated-fact ground: full flip
    assert flags[0]["scene_ids"] == ["S004", "S084"]  # widened to where the fact is stated


def test_unstated_fact_overturn_reads_names_from_the_finding():
    """Run 12: the rejection said only 'the daughters' — no names — so the anchor
    names must come from the FINDING, tied to the claimed numbers there."""
    from greenlight.agents.verification import _stated_fact_overturn

    state = _daughters_state()
    reason = (
        "The claim relies on unstated script facts by asserting specific ages "
        "(ages 2 and 4) for the daughters in S084, violating the rule against "
        "multi-step inference regarding character ages."
    )
    finding = (
        "Scene S084 features two young toddler daughters (Haylee, age 2, and "
        "Kaitlin, age 4) running through a wedding crowd."
    )
    assert _stated_fact_overturn(reason, state, finding) == ("Haylee, Kaitlin", "S004")
    assert _stated_fact_overturn(reason, state) is None  # without the finding: no anchor


def test_mixed_grounds_strikes_false_ground_but_does_not_flip():
    """A rejection standing on BOTH a false unstated-fact ground AND a real
    sourcing ground must not blind-flip to SUPPORTED — strike the false ground,
    keep the rejection as premise_unsupported so it demotes honestly."""
    from greenlight.agents.verification import _apply_overturns

    state = _daughters_state()
    reason = (
        "The claim asserts unstated ages (ages 2 and 4) for the daughters in S084. "
        "Furthermore, the cited excerpts do not establish the asserted labor statutes."
    )
    flags = [
        {
            "flag_id": "F3009",
            "scene_ids": ["S084"],
            "category": "minor_safety",
            "finding": "Two toddler daughters (Haylee, age 2, and Kaitlin, age 4) on set.",
        }
    ]
    verdicts = {"F3009": {"verdict": "UNSUPPORTED", "reason": reason}}
    out = _apply_overturns(flags, verdicts, state)
    v = verdicts["F3009"]
    assert v["verdict"] == "UNSUPPORTED"  # sourcing ground stands
    assert v["failure_mode"] == "premise_unsupported"  # -> demotes to open questions
    assert v.get("ground_overturned") and "S004" in v["reason"]
    assert out and "struck" in out[0][1]
    assert flags[0]["scene_ids"] == ["S004", "S084"]  # coordinates still widened


def test_coordinate_completion_widens_before_verification():
    """Run-13 item 4: the finding's number-anchored claims resolve to scenes
    BEFORE the verifier judges — the ages live in S004, the finding declared
    S084 only. Widening happens upstream; the verdict then means something."""
    from greenlight.agents.verification import _complete_coordinates

    state = _daughters_state()
    flag = {
        "flag_id": "F3009",
        "scene_ids": ["S084"],
        "finding": "Two toddler daughters (Haylee, age 2, and Kaitlin, age 4) appear "
        "in S084. Under NRS 609 and 8 CCR 11755, children aged 2 to 5 are limited "
        "to 3 hours on set, and permits cost $500.",
    }
    added = _complete_coordinates(flag, state)
    assert flag["scene_ids"] == ["S004", "S084"]  # widened to where the ages are stated
    assert added and added[0][0] == "S004"
    # premise figures never anchor: 609, 11755 (4+ digits, excluded), 3-hour cap
    # near CCR context, $500 — none appear in the additions
    nums_used = {a[1] for a in added}
    assert nums_used <= {"2", "4"}


def test_coordinate_completion_ignores_premise_figures_and_ambiguity():
    from greenlight.agents.verification import _complete_coordinates, _scriptfact_nums

    # statutes, money, percents, census tallies are premise figures
    assert (
        _scriptfact_nums(
            "under NRS 609 and 29 CFR 1910, costs $15,000, 62% of films, 'shit' x8 spoken"
        )
        == set()
    )
    # a claim whose anchors appear in no scene widens nothing
    state = _daughters_state()
    flag = {
        "flag_id": "F1",
        "scene_ids": ["S084"],
        "finding": "Melissa, age 9, and Teddy, age 7, are depicted.",
    }
    assert _complete_coordinates(flag, state) == []
    assert flag["scene_ids"] == ["S084"]


def test_cutlist_scrub_keeps_actions_and_fails_visible():
    """Post-reconcile beats carry rule clauses the filing gate never saw. The
    scrub strips the clause and keeps the action; a beat it cannot cleanly fix
    ships UNMODIFIED and is reported as a miss — never mangled, never deleted."""
    from greenlight.agents.verification import _scrub_cutlist

    beats = [
        "Cut the spoken 'fucking' in S084, retaining at most 1 non-sexual use.",
        "Restage the S055 bull sequence as slapstick.",  # clean: untouched
        "Conform to PG-13 language limits.",  # the clause IS the beat: miss
    ]
    out, misses = _scrub_cutlist(beats)
    assert len(out) == 3  # never deletes a beat
    assert out[0] == "Cut the spoken 'fucking' in S084."  # action survives
    assert out[1] == beats[1]
    assert out[2] == beats[2]  # unmodified, fail visible
    assert len(misses) == 1 and misses[0][0] == beats[2]


def test_misstatement_facts_collected_from_rejections():
    """Fact propagation's deterministic half: script_misstatement rejections yield
    (scenes, fact); sourcing failures contribute nothing."""
    from greenlight.agents.verification import _misstatement_facts

    dropped = [
        {
            "flag_id": "F4012",
            "failure_mode": "script_misstatement",
            "scene_ids": ["S066", "S068"],
            "rejection_reason": "In S066 the vehicle is stationary and parked; "
            "in S068 the car is already stopped. Nobody drinks while driving.",
        },
        {
            "flag_id": "F4011",
            "failure_mode": "premise_unsupported",
            "scene_ids": ["S008"],
            "rejection_reason": "The excerpts do not establish the UAE rule.",
        },
    ]
    facts = _misstatement_facts(dropped)
    assert len(facts) == 1
    sids, reason = facts[0]
    assert sids == {"S066", "S068"} and "parked" in reason


def test_unstated_fact_overturn_is_precise():
    from greenlight.agents.verification import _stated_fact_overturn

    state = _daughters_state()
    # ages the script does not state near the names must NOT overturn
    assert _stated_fact_overturn("Unstated: Haylee and Kaitlin are age 7 and age 9.", state) is None
    # a single name cannot anchor a co-occurrence overturn
    assert _stated_fact_overturn("Does not specify Haylee's age; unstated.", state) is None
    # a genuine absence ruling is the other mechanism's job, not this one
    assert _stated_fact_overturn("The tiger does not appear anywhere in the script.", state) is None


def test_absent_terms_stems_do_not_punish_paraphrase():
    """Run 6: F205 died because 'bloody'/'gunfire' aren't literal — on a page
    with 'his lip explodes with blood'. Stems keep morphology out."""
    from greenlight.agents.verification import _absent_terms

    script = "he pistol-whips vick -- his lip explodes with blood. the guamians open fire."
    absent = _absent_terms("Bloody violence as automatic gunfire erupts near a tiger.", script)
    assert "bloody" not in absent  # blood is on the page
    assert "tiger" in absent  # contamination still caught

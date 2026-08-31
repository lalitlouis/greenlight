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
    assert _stated_fact_overturn(reason, state) == ("Haylee, Kaitlin, Stu", "S004")
    flags = [{"flag_id": "F3011", "scene_ids": ["S084"], "category": "minor_safety"}]
    _apply_overturns(flags, {"F3011": {"verdict": "UNSUPPORTED", "reason": reason}}, state)
    assert flags[0]["scene_ids"] == ["S004", "S084"]  # widened to where the fact is stated


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

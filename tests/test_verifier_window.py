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

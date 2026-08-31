"""Parser tests against the real fixture screenplay. No API calls."""

from itertools import pairwise
from pathlib import Path

import pytest

from greenlight.contracts import ContractViolation, validate
from greenlight.parser import annotated_script, parse_fountain, strip_title_page

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "slack_tide.fountain"
SOURCE = FIXTURE.read_text()


@pytest.fixture(scope="module")
def parsed():
    return parse_fountain(SOURCE)


def test_title_page(parsed):
    meta, _ = parsed
    assert meta["title"] == "SLACK TIDE"
    assert "greenlight" in meta["author"].lower()


def test_scene_count_and_ids(parsed):
    _, scenes = parsed
    assert len(scenes) == 12
    assert [s["scene_id"] for s in scenes] == [f"S{i:03d}" for i in range(1, 13)]


def test_raw_spans_are_exact_slices(parsed):
    """The invariant the marked-up script view depends on: spans tile the body."""
    _, scenes = parsed
    for a, b in pairwise(scenes):
        assert a["raw_span"][1] == b["raw_span"][0]
    assert scenes[-1]["raw_span"][1] == len(SOURCE)
    for s in scenes:
        start, end = s["raw_span"]
        assert SOURCE[start:end].strip().startswith(s["heading"])


def test_headings_parsed(parsed):
    _, scenes = parsed
    first = scenes[0]
    assert first["int_ext"] == "EXT"
    assert first["location"] == "PORT BANNOCK HARBOR"
    assert first["time_of_day"] == "DAWN"
    combo = next(s for s in scenes if s["int_ext"] == "INT/EXT")
    assert combo["location"] == "MARGARET ROSE - WHEELHOUSE"
    assert "CONTINUOUS" in combo["time_of_day"]


def test_dialogue_and_characters(parsed):
    _, scenes = parsed
    wheelhouse = scenes[1]
    assert "CROW" in wheelhouse["characters"]
    assert "MARA" in wheelhouse["characters"]
    crow_lines = [d["line"] for d in wheelhouse["dialogue"] if d["character"] == "CROW"]
    assert any("Coors Light" in line for line in crow_lines)
    # (CONT'D) folds into the same character, never a new one
    assert not any("CONT" in c for s in scenes for c in s["characters"])


def test_seeded_content_is_findable(parsed):
    """The seeds the desks must find are present in parsed scenes (see SEEDS.md)."""
    _, scenes = parsed
    all_text = " ".join(
        s["action"] + " " + " ".join(d["line"] for d in s["dialogue"]) for s in scenes
    )
    lowered = all_text.lower()
    for seed in [
        "hallelujah",
        "jeff buckley",
        "stephen foster",
        "thermos",
        "nighthawks",
        "coast guard",
    ]:
        assert seed in lowered, f"seed {seed!r} lost in parsing"
    assert all_text.lower().count("fuck") == 3  # ratings bookkeeping invariant


def test_page_numbers_monotonic(parsed):
    _, scenes = parsed
    pages = [s["page"] for s in scenes]
    assert pages == sorted(pages)
    assert 8 <= pages[-1] <= 18  # ~13pp screenplay; the model is crude, the range is not


def test_annotated_script_has_ids(parsed):
    _, scenes = parsed
    annotated = annotated_script(SOURCE, scenes)
    assert "[S001] EXT. PORT BANNOCK HARBOR - DAWN" in annotated
    assert annotated.count("[S0") == len(scenes)


def test_scene_schema_rejects_bad_scene():
    with pytest.raises(ContractViolation):
        validate("scene", {"scene_id": "bogus"})


def test_no_title_page_is_fine():
    meta, offset = strip_title_page("INT. NOWHERE - DAY\n\nNothing happens.\n")
    assert meta == {} and offset == 0


def test_adaptation_context_detection():
    from greenlight.pipeline import adaptation_context

    meta = {"title": "X", "source": "Based on The Accidental Billionaires by Ben Mezrich"}
    assert "Mezrich" in adaptation_context(meta, None)
    # user-provided context leads; title-page source appends; dedupe holds
    both = adaptation_context(meta, "Life rights: none acquired.")
    assert both.startswith("Life rights: none acquired.") and "Mezrich" in both
    assert adaptation_context({"title": "X"}, None) == ""
    # a 'based on' line under any key is caught
    assert "novel" in adaptation_context({"notes": "based on the novel"}, None)


def test_form_feeds_anchor_real_pages():
    """PDF sources carry \f page breaks; scenes must use the REAL page, not
    the 55-line estimate (which drifted 17 pages by act three on a feature)."""
    from greenlight.parser import parse_fountain

    text = (
        "INT. ROOM A - DAY\n\nShort scene.\n\n\f\n"
        "INT. ROOM B - NIGHT\n\nAnother.\n\n\f\n\f\n"
        "INT. ROOM C - DAY\n\nDeep in the script.\n"
    )
    _, scenes = parse_fountain(text)
    assert [s["page"] for s in scenes] == [1, 2, 4]


def test_buried_heading_promoted_only_when_location_is_known():
    """A prefix-less location line is a scene heading the writer left unmarked; it is
    promoted only when the script names that location elsewhere with a real INT./EXT.
    prefix (the Hangover rooftop/suite merge — a bare 'THE DEAN MARTIN SUITE' absorbed
    the suite scene under the rooftop slugline, mis-anchoring every flag there).
    Character cues and stray all-caps lines match no known location and must NOT mint
    phantom scenes."""
    text = (
        "EXT. MANDALAY BAY ROOFTOP -- NIGHT\n\n"
        "The guys drink on the ledge.\n\n"
        "STU\nThis is a bad idea.\n\n"
        "THE DEAN MARTIN SUITE\n\n"  # buried heading: base location known below -> promoted
        "A live chicken wanders across the trashed suite.\n\n"
        "INT. THE DEAN MARTIN SUITE -- MOMENTS LATER\n\n"
        "They regroup.\n"
    )
    _, scenes = parse_fountain(text)
    headings = [s["heading"] for s in scenes]
    assert headings.count("THE DEAN MARTIN SUITE") == 1  # promoted exactly once
    roof = next(s for s in scenes if "ROOFTOP" in s["heading"])
    assert "chicken" not in " ".join(roof["action"]).lower()  # suite content split out


def test_bare_allcaps_without_known_location_stays_in_scene():
    """Bare all-caps lines are overwhelmingly character cues, not headings (1093 of
    them in the real script); without a base-location match none may mint a scene."""
    text = (
        "INT. OFFICE -- DAY\n\n"
        "She reads the memo.\n\n"
        "MARGARET\nWe ship tonight.\n\n"  # cue: base 'MARGARET' matches no location
        "THE BIG REVEAL\n\n"  # stray all-caps: base matches no location
        "Everyone gasps.\n"
    )
    _, scenes = parse_fountain(text)
    assert len(scenes) == 1
    assert scenes[0]["heading"] == "INT. OFFICE -- DAY"


def test_title_page_feeds_do_not_shift_printed_pages():
    """A PDF title page occupies page 1 of the FILE but page 0 of the printed
    script — scene pages must match the printed numbering (+1 bug, run 3)."""
    from greenlight.parser import parse_fountain

    text = (
        "Title: THE HANGOVER\nAuthor: L\n\n\f\n"
        "INT. ROOM A - DAY\n\nAction.\n\n\f\n"
        "INT. ROOM B - NIGHT\n\nMore.\n"
    )
    _, scenes = parse_fountain(text)
    assert [s["page"] for s in scenes] == [1, 2]


def test_attached_title_separator_feed_does_not_shift_pages():
    """PDF extractors put the form feed at the START of the next page's first
    line ("\\fINT. ..."), so the title->page-1 separator sits after body_start.
    Run 4 (third flagging): every scene page ran exactly +1 because that feed
    was counted as a body page break."""
    from greenlight.parser import parse_fountain, printed_page_count

    text = (
        "Title: THE HANGOVER\nAuthor: L\n\n"
        "\fINT. ROOM A - DAY\n\nAction.\n\n"
        "\fINT. ROOM B - NIGHT\n\nMore.\n"
    )
    _, scenes = parse_fountain(text)
    assert [s["page"] for s in scenes] == [1, 2]
    assert printed_page_count(text) == 2


def test_printed_page_count_includes_pages_after_last_scene():
    """The header read 110 pp against a real 111: max(scene page) misses
    printed pages after the final scene heading."""
    from greenlight.parser import printed_page_count

    text = (
        "Title: X\nAuthor: L\n\n"
        "\fINT. ROOM A - DAY\n\nAction.\n\n"
        "\fMore action, no new scene.\n\n"
        "\fTHE END\n"
    )
    assert printed_page_count(text) == 3
    assert printed_page_count("no feeds here") is None


def test_display_title_page_without_fountain_meta():
    """The REAL failure shape, four runs running: a PDF title page is display
    text ('THE HANGOVER / Written by / ...'), not Fountain Key: metadata — any
    meta-gated front-matter logic silently never fires. Structural detection
    must classify it, and an attached feed on the heading's own line still
    counts as that page's leading feed."""
    from greenlight.parser import parse_fountain, printed_page_count

    text = (
        "THE HANGOVER\nWritten by\nJon Lucas & Scott Moore\nSeptember 30, 2007\n"
        "\f\nEXT. BEL AIR BAY CLUB -- MORNING\n\nWorkers bustle about the lawn.\n"
        "\f\nINT. BRIDAL SUITE -- DAY\n\nDresses everywhere.\n"
        "\f\nTHE END\n"
    )
    _, scenes = parse_fountain(text)
    assert [s["page"] for s in scenes] == [1, 2]
    assert printed_page_count(text) == 3


# --- run-7 review: cue false positives (C3), page edges (C2/C7) --------------


def test_contd_curly_apostrophe_folds_to_the_speaker():
    """The real script writes CONT'D with a curly apostrophe; the straight-quote
    stripper never matched it, minting 'STEVE (CONT\u2019D)' as a separate character."""
    from greenlight.parser import _CUE_EXTENSION_RE, _is_cue

    assert _CUE_EXTENSION_RE.sub("", "STEVE (CONT\u2019D)").strip() == "STEVE"
    assert _is_cue("STEVE (CONT\u2019D)", "Right this way.")


def test_action_lines_are_not_character_cues():
    from greenlight.parser import _is_cue

    nxt = "and the crowd roars."
    assert not _is_cue("ANNND ON STAGE ONE, PUT YOUR HANDS", nxt)  # comma + long
    assert not _is_cue("THEY\u2019RE CLOTHESLINED BY TWO CHAIRS", nxt)  # 5 words
    assert not _is_cue("TOGETHER FOR...DOUBLE STAXXX!", nxt)  # ends with !
    # real cues still pass
    assert _is_cue("VICK", "What?") and _is_cue("OFFICER BLADEN", "Step out.")


def test_printed_page_count_ignores_a_trailing_form_feed():
    """pdftotext emits a feed after EVERY page including the last, leaving a
    trailing empty segment that is not a page (+1 overcount)."""
    from greenlight.parser import printed_page_count

    no_trailing = "INT. A - DAY\n\nx\n\fINT. B - DAY\n\ny\n"
    trailing = no_trailing + "\f"
    assert printed_page_count(trailing) == printed_page_count(no_trailing)


def test_cold_open_prose_page_is_not_front_matter():
    """A cold open ('OVER BLACK / a phone rings in the dark') is page 1, not a
    title page — misclassifying it shifted every scene page -1."""
    from greenlight.parser import parse_fountain, printed_page_count

    text = (
        "OVER BLACK\na phone rings somewhere in the dark room.\n"
        "\fINT. APARTMENT - NIGHT\n\nShe answers.\n"
    )
    _, scenes = parse_fountain(text)
    # the cold open IS page 1 (no slugline), so INT. APARTMENT is page 2 —
    # before the fix the cold open was miscounted as front matter and the
    # scene collapsed to page 1, undercounting the whole script by one
    assert scenes[0]["page"] == 2
    assert printed_page_count(text) == 2


def test_title_page_still_reads_as_front_matter():
    """The prose guard must not misfire on a real title page (no running
    sentence): 'THE HANGOVER / Written by / ... / September 30, 2007'."""
    from greenlight.parser import _looks_like_front_matter

    assert _looks_like_front_matter("THE HANGOVER\nWritten by\nJon Lucas & Scott Moore\n2007")

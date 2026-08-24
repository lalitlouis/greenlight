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

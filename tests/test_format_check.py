"""Format desk is deterministic — test it like the parser. No API calls."""

from pathlib import Path

from greenlight.parser import parse_fountain
from greenlight.writer.format_check import format_report

SOURCE = (Path(__file__).resolve().parents[1] / "fixtures" / "slack_tide.fountain").read_text()


def test_format_report_on_fixture():
    meta, scenes = parse_fountain(SOURCE)
    rep = format_report(meta, scenes, SOURCE)
    by_id = {c["id"]: c for c in rep["checks"]}
    assert by_id["length"]["status"] == "INFO"  # ~13pp: short-film territory
    assert by_id["title_page"]["status"] == "PASS"
    assert by_id["headings"]["status"] == "PASS"
    assert rep["stats"]["scenes"] == 12
    assert rep["stats"]["cast"] >= 6
    assert 0 < rep["stats"]["dialogue_ratio"] < 1
    assert rep["counts"]["PASS"] >= 3


def test_format_report_is_deterministic():
    meta, scenes = parse_fountain(SOURCE)
    assert format_report(meta, scenes, SOURCE) == format_report(meta, scenes, SOURCE)


def test_missing_title_page_warns():
    src = "INT. NOWHERE - DAY\n\nSomething happens.\n\nBOB\nHello.\n"
    meta, scenes = parse_fountain(src)
    rep = format_report(meta, scenes, src)
    by_id = {c["id"]: c for c in rep["checks"]}
    assert by_id["title_page"]["status"] == "WARN"

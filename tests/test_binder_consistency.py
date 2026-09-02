"""The binder is a faithful projection of the report — asserted, not hoped.

Confirmed failure modes this gate exists to prevent (2026-08-27 review):
a territory fold silently dropped finding F403; the header claimed one more
MEDIUM than the table rendered; six cells were sliced mid-word; Item
duplicated Category on every desk row without an entity.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pytest

from greenlight import binder

ROOT = Path(__file__).resolve().parents[1]
RECORDS = sorted(glob.glob(str(ROOT / "runs" / "case_*.json")))


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text())


@pytest.mark.parametrize("path", RECORDS, ids=[Path(p).stem for p in RECORDS])
def test_binder_matches_report(path: str) -> None:
    record = _load(path)
    b = binder.build(record, {})
    rows = [r for r in b["rows"] if r["Finding"]]

    cited = [f for f in record.get("flags", []) if f.get("citations")]
    by_id = {f["flag_id"]: f for f in cited}

    # Every kept finding renders exactly once; nothing extra appears.
    rendered_ids = [r["Finding"] for r in rows]
    assert sorted(rendered_ids) == sorted(by_id), (
        f"binder rows diverge from report findings in {Path(path).name}"
    )
    assert len(rendered_ids) == len(set(rendered_ids)), "a finding rendered twice"

    for r in rows:
        f = by_id[r["Finding"]]
        # Severity and cost are copied, never re-derived.
        assert r["Severity"] == f.get("severity", "")
        cost = (f.get("remedy") or {}).get("est_cost_usd") or []
        if len(cost) == 2 and all(isinstance(c, (int, float)) for c in cost) and cost[1] > 0:
            assert str(f"{cost[0]:,.0f}").split(".")[0].replace(",", "") in r[
                "Est. cost (USD)"
            ].replace(",", ""), f"cost range missing for {r['Finding']}"
        # The finding text (where corrected titles live) is present in the note.
        if f.get("finding") and len(r["Remedy / licensing note"]) < 2400:
            assert str(f["finding"]) in r["Remedy / licensing note"], (
                f"finding text elided in binder note for {r['Finding']}"
            )
        # No mid-word slice: a clipped cell ends with the ellipsis marker.
        note = r["Remedy / licensing note"]
        assert len(note) <= 2400 or note.endswith("…")
        # the remedy is the actionable half — it must be present, uncut
        detail = (f.get("remedy") or {}).get("detail") or ""
        if detail and len(note) < 2400:
            assert detail[:60] in note, f"remedy truncated for {r['Finding']}"
        # Item never silently duplicates Category.
        if r["Item"] != "—":
            assert r["Item"] != r["Category"]

    # The header counts describe this table, not some other artifact.
    from collections import Counter

    assert b["counts"] == dict(Counter(r["Severity"] for r in rows if r["Severity"]))


def test_at_least_one_record_present() -> None:
    assert RECORDS, "no case records found — the gate is vacuously passing"


# ---- 2026-09-01 review (B9/B13/B17): print-surface parity and no truncation -----


def _mini_record(**over) -> dict:
    flags = [
        {
            "flag_id": "F100",
            "agent": "safety_underwriter",
            "category": "stunt_pyro",
            "severity": "BLOCKER",
            "scene_ids": ["S001"],
            "finding": "Fire on a boat.",
            "remedy": {
                "action": "ADD_SPECIALIST",
                "detail": "Hire a pyro coordinator.",
                "est_cost_usd": [1000, 2000],
            },
            "citations": [{"url": "https://csatf.org/x", "excerpt": "Pyro bulletin text."}],
            "verification_unavailable": True,
        },
        {
            "flag_id": "F101",
            "agent": "clearance_counsel",
            "category": "trademark_use",
            "severity": "MEDIUM",
            "scene_ids": ["S002"],
            "entity_id": "E1",
            "finding": "A brand is shown.",
            "remedy": {"action": "REPLACE", "detail": "Swap the label.", "est_cost_usd": [0, 300]},
            "citations": [{"url": "https://example.gov/x", "excerpt": "Trademark text."}],
        },
    ]
    rec = {
        "script_title": "A <Boat> & A Bar\nSecond line",
        "generated_at": "2026-09-01T00:00:00",
        "entities": [
            {"entity_id": "E1", "surface": "Coors Light"},
            {"entity_id": "E2", "surface": "Ford"},
        ],
        "flags": flags,
        "rejected_flags": [],
        "cleared": {
            "clearance_counsel": [
                {"entity_id": "E2", "reasoning": "No known issue for this mention."},
            ]
        },
        "open_questions": {},
        "oq_followups": {"F101": ["Confirm the label variant used on set."]},
        "entity_accounting": {"body_flagged_ids": ["E2"], "fold": {}, "fragment_ids": []},
        "report": {
            "greenlight_score": None,
            "verification_degraded": True,
            "est_clearance_cost_usd": [1000, 2300],
            "est_cost_paths": {
                "as_written": [1000, 2300],
                "target_rating": [1000, 2000],
                "excluded": [],
            },
        },
    }
    rec.update(over)
    return rec


_META = {
    f"S{i:03d}": {"heading": f"INT. PLACE {i}", "page": i, "number": str(i)} for i in (1, 2, 3)
}


def test_fail_open_flag_is_marked_on_binder_rows_and_disclaimer() -> None:
    b = binder.build(_mini_record(), _META)
    row = next(r for r in b["rows"] if r["Finding"] == "F100")
    assert row["Clearance status"].startswith("UNVERIFIED (verifier unavailable)")
    assert "DO NOT SHOOT" in row["Clearance status"]  # severity language still present
    assert b["unverified_rows"] == 1
    assert "UNVERIFIED" in b["disclaimer"]
    top = next(t for t in b["top_exposures"] if t["finding"] == "F100")
    assert top["unverified"] is True
    # a verified row carries no marker
    other = next(r for r in b["rows"] if r["Finding"] == "F101")
    assert not other["Clearance status"].startswith("UNVERIFIED")


def test_withheld_cause_and_cost_paths_travel_with_the_binder() -> None:
    b = binder.build(_mini_record(), _META)
    assert b["score"] is None
    assert b["verification_degraded"] is True
    assert b["est_cost_paths"]["target_rating"] == [1000, 2000]
    # the PDF header prints both paths from the same data
    from greenlight import pdfgen

    line = pdfgen.cost_paths_label(b["est_cost"], b["est_cost_paths"])
    assert "as written $1,000" in line and "$2,300" in line
    assert "target-rating path $1,000" in line and "$2,000" in line
    assert pdfgen.score_label(None, True) == "WITHHELD (verification unavailable)"
    assert pdfgen.score_label(None, False) == "WITHHELD (analysis incomplete)"
    assert pdfgen.score_label(42, False) == "42/100"


def test_followup_travels_with_its_finding_row() -> None:
    b = binder.build(_mini_record(), _META)
    row = next(r for r in b["rows"] if r["Finding"] == "F101")
    assert "Open point on this finding: Confirm the label variant" in row["Remedy / licensing note"]


def test_body_flagged_no_issue_row_is_suppressed_like_the_web() -> None:
    bm = binder._back_matter(_mini_record())
    texts = [c["text"] for c in bm["cleared"]]
    assert not any("Ford" in t for t in texts if "further determination" not in t)
    assert any("further determination" in t for t in texts)


def test_scene_labels_are_never_truncated() -> None:
    from greenlight.binder import _compact_scene_ref, _scene_ref

    sids = [f"S{i:03d}" for i in range(1, 30)]
    numbers = {s: str(i) for i, s in enumerate(sids, start=1)}
    assert _scene_ref(sids, numbers) == "Sc. 1-29"
    assert "more" not in _scene_ref(sids[:9], numbers)
    assert _scene_ref(["S001", "S002", "S009"], numbers) == "Sc. 1-2, 9"
    # a non-numeric script label prints every label, no cap
    mixed = {"S001": "1", "S002": "2A", "S003": "3"}
    assert _scene_ref(["S001", "S002", "S003"], mixed) == "Sc. 1, 2A, 3"
    # generated ids: 29 disjoint ranges, none hidden
    odd = [f"S{i:03d}" for i in range(1, 60, 2)]
    ref = _compact_scene_ref(odd)
    assert "more" not in ref and ref.count("S") == len(odd)


def test_scene_coverage_counts_built_rows() -> None:
    b = binder.build(_mini_record(), _META)
    assert b["scene_coverage"] == {"scenes": 3, "scenes_with_rows": 3}
    assert len({r["_scene_id"] for r in b["rows"]}) == 3
    # a row per scene is the contract the coverage number is derived from
    assert sorted({r["_scene_id"] for r in b["rows"]}) == sorted(_META)


def test_unknown_severity_does_not_crash_the_sort() -> None:
    rec = _mini_record()
    rec["flags"][1]["severity"] = "WEIRD"
    b = binder.build(rec, _META)
    assert any(r["Finding"] == "F101" for r in b["rows"])


def test_csv_header_cannot_be_injected_by_a_title_newline() -> None:
    b = binder.build(_mini_record(), _META)
    csv_text = binder.to_csv(b)
    head = csv_text.splitlines()[0]
    assert head.startswith("# A <Boat> & A Bar Second line")
    # the two comment lines are followed directly by the header row
    assert csv_text.splitlines()[2].startswith("Scene,")

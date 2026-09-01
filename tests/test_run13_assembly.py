"""Run-13 batch C: cleared-path transforms, binder scene coverage, cost
attribution, title precedence. All deterministic display/assembly logic."""

from greenlight import binder, entity_accounting
from greenlight.parser import detect_structural_title
from greenlight.report import _cost_paths


def _record():
    return {
        "entities": [
            {"entity_id": "E001", "surface": "Alan Mervish", "scene_ids": ["S010"]},
            {"entity_id": "E002", "surface": "I (cid:60) ROGER", "scene_ids": ["S011"]},
            {"entity_id": "E003", "surface": "Sbarro", "scene_ids": ["S012"]},
            {"entity_id": "E004", "surface": "MGM Resorts", "scene_ids": ["S013"]},
        ],
        "unexamined": [],
        "flags": [
            {
                "flag_id": "F1016",
                "entity_id": None,
                "finding": "Name-commonality exposure for Alan Mervish and others.",
                "remedy": {"detail": "Negotiate with MGM Resorts management."},
                "citations": [{"excerpt": "x"}],
                "scene_ids": ["S010"],
                "severity": "LOW",
                "category": "name_clearance",
            }
        ],
        "cleared": {
            "clearance_counsel": [
                # named in a finding BODY -> suppression index (renderer-side)
                {"entity_id": "E001", "reasoning": "Negative check confirmed for Alan Mervish."},
                # work claim WITH a batch-sweep receipt -> stands
                {"entity_id": "E003", "reasoning": "Search confirms no registered conflict."},
                # work claim, NO receipt -> rewritten
                {"entity_id": "E004", "reasoning": "Negative check confirmed; no issues."},
            ]
        },
        "research": {
            "research:EBATCH:abc": {
                "objective": "Name-commonality sweep for Sbarro and other marks",
                "queries": "['sbarro trademark']",
            }
        },
        "entity_accounting": {},
    }


def test_polish_record_cid_bodyflags_and_receipted_rewrites():
    rec = _record()
    entries = entity_accounting.polish_record(rec)
    # 6a: cid stripped from the display surface
    assert rec["entities"][1]["surface"] == "I ROGER"
    # 1a: body-named subject indexed; the REMEDY-named counterparty (MGM) is NOT
    body = rec["entity_accounting"]["body_flagged_ids"]
    assert "E001" in body and "E004" not in body
    dets = rec["cleared"]["clearance_counsel"]
    # 1b: batch-sweep receipt protects the true claim
    assert "Search confirms" in dets[1]["reasoning"] and not dets[1].get("rephrased")
    # 1b: unreceipted work claim is rewritten, honestly and visibly
    assert dets[2].get("rephrased") and "No research trace" in dets[2]["reasoning"]
    assert any(e["guard"] == "cleared_rephrase" for e in entries)


def test_binder_emits_a_row_for_every_scene():
    """S050 vanished because a scene covered by a finding anchored elsewhere
    emitted NOTHING. Every scene emits a row; covered scenes cross-reference."""
    rec = {
        "scene_meta": {
            "S001": {"heading": "INT. A", "page": 1, "number": ""},
            "S002": {"heading": "INT. B", "page": 2, "number": ""},
            "S003": {"heading": "INT. C", "page": 3, "number": ""},
        },
        "entities": [],
        "flags": [
            {
                "flag_id": "F100",
                "scene_ids": ["S001", "S002"],
                "finding": "A finding argued from S001.",
                "remedy": {},
                "citations": [{"excerpt": "x"}],
                "severity": "HIGH",
                "category": "test",
            }
        ],
        "rejected_flags": [],
        "cleared": {},
        "open_questions": {},
        "report": {},
    }
    built = binder.build(rec)
    cov = built["scene_coverage"]
    assert cov == {"scenes": 3, "scenes_with_rows": 3}
    rows = built["rows"]
    statuses = {r["Scene heading"]: r["Clearance status"] for r in rows}
    assert "Covered by F100" in statuses["INT. B"]  # cross-reference, not silence
    assert statuses["INT. C"] == "No known issue"


def test_cost_paths_excluded_sums_to_the_delta():
    flags = [
        {
            "flag_id": "F1",
            "category": "sync_license",
            "remedy": {"est_cost_usd": [40000, 80000]},
            "cost_excluded_on_target_path": True,
        },
        {
            "flag_id": "F2",
            "category": "location_release",
            "remedy": {"est_cost_usd": [5000, 10000]},
        },
    ]
    paths = _cost_paths(flags)
    assert paths["excluded"] == [
        {"flag_id": "F1", "category": "sync_license", "est_cost_usd": [40000, 80000]}
    ]
    lo = sum(x["est_cost_usd"][0] for x in paths["excluded"])
    hi = sum(x["est_cost_usd"][1] for x in paths["excluded"])
    assert [
        paths["as_written"][0] - paths["target_rating"][0],
        paths["as_written"][1] - paths["target_rating"][1],
    ] == [lo, hi]


def test_structural_title_from_pdf_front_matter():
    pdf_like = (
        "THE HANGOVER\nWritten by\nJon Lucas & Scott Moore\n\x0c\nEXT. CLUB -- MORNING\nAction.\n"
    )
    assert detect_structural_title(pdf_like) == "The Hangover"
    # a cold open with no front matter claims nothing
    assert detect_structural_title("EXT. STREET - DAY\n\nA car rolls by.\n") is None
    # Fountain metadata is handled upstream — this helper stands down
    assert detect_structural_title("Title: SLACK TIDE\n\nINT. BAR - DAY\n\nHi.\n") is None
    # a prose first line is not a title
    assert (
        detect_structural_title("a quiet morning in the palisades.\n\x0c\nINT. A - DAY\nx.\n")
        is None
    )

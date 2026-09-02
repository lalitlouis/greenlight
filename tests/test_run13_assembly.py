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


# ---- review 2026-09-01 (Worker 4A): the shared eval invariants ---------------


def _invariants():
    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "eval_invariants.py"
    spec = importlib.util.spec_from_file_location("eval_invariants", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_term_arithmetic_catches_the_off_by_one_and_allows_pd_from():
    inv = _invariants()
    bad = "Created in 1942, the artwork remains protected through 2038 (95 years post-publication)."
    assert inv.term_arithmetic_problems(bad) == [
        "1942 + 95 years is through 2037, text says through 2038"
    ]
    assert (
        inv.term_arithmetic_problems(
            "Published 1942; 95 years of protection, so it enters the public domain in 2038."
        )
        == []
    )
    assert inv.term_arithmetic_problems("Protected through 2037 (95 years from 1942).") == []
    # a stunt's rehearsal hours and a 1968 film with no expiry: nothing to check
    assert inv.term_arithmetic_problems("4 hours of rehearsal; the 1968 film.") == []


def test_rightsholder_names_must_trace_to_the_findings_own_excerpts():
    inv = _invariants()
    flag = {
        "category": "sync_license",
        "finding": (
            "Sync license from Sony Music Publishing (controlling the catalog / Badams "
            "Music); Legacy Recordings holds the master."
        ),
        "remedy": {"detail": ""},
        "citations": [{"excerpt": "Hallelujah — Copyright Sony/ATV Music Publishing"}],
    }
    assert inv.untraceable_rightsholders(flag) == ["Badams Music", "Legacy Recordings"]


def test_scene_labels_expand_to_scene_ids():
    inv = _invariants()
    assert inv.expand_scene_label("S002, S004-S005, S009", {}) == {
        "S002",
        "S004",
        "S005",
        "S009",
    }
    nums = {"1": "S001", "2": "S002", "3": "S003", "9": "S009"}
    assert inv.expand_scene_label("Sc. 1-3, 9", nums) == {"S001", "S002", "S003", "S009"}


def test_shared_invariants_flag_cut_list_direction_and_phantom_references():
    inv = _invariants()
    flag = {
        "flag_id": "F1",
        "agent": "ratings_board",
        "category": "rating_language",
        "severity": "HIGH",
        "scene_ids": ["S001"],
        "finding": "Three F-words in S001; see F700 for the drug driver.",
        "remedy": {"detail": "", "est_cost_usd": [0, 0]},
        "citations": [{"excerpt": "x"}],
        "marginal": {"descriptor": "language", "n": 1, "distribution": {}, "source": "s"},
    }
    rec = {
        "flags": [flag],
        "rejected_flags": [],
        "verdicts": {"F1": {"verdict": "SUPPORTED"}},
        "scene_meta": {"S001": {"heading": "INT. BAR", "number": ""}},
        "cleared": {},
        "open_questions": {},
        "report": {
            "greenlight_score": 50,
            "counts": {"HIGH": 1},
            "by_agent": {"ratings_board": 1},
            "est_clearance_cost_usd": [0, 0],
            "rating_prediction": {
                "predicted": "R",
                "target": "R",
                "beats_to_cut": ["Cut the F-words"],
                "comparables": [],
                "conformal_set": ["R"],
            },
        },
    }
    results = {name: (ok, note) for name, ok, note in inv.shared_invariants(rec)}
    assert results["invariant: cut list present iff the prediction exceeds the target"][0] is False
    key = (
        "invariant: no cleared/open-question/finding text cites an id that neither renders "
        "nor is rejected"
    )
    assert results[key][0] is False and "F700" in results[key][1]
    assert results["invariant: counts, by_agent, cost, days and pages reconcile with the flags"][0]

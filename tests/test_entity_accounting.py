"""Headline entity accounting (run-4 review: ~20 of '78 entities researched'
were fragments or duplicates) and binder row anchoring/cleared honesty."""

from greenlight.binder import _argued_scene
from greenlight.entity_accounting import account


def ents(*surfaces):
    return [{"entity_id": f"E{i}", "surface": s} for i, s in enumerate(surfaces)]


def test_account_folds_reviewers_exact_examples():
    out = account(
        ents(
            "Vick",
            "Alan",
            "Vick and Alan",
            "Stu and Vick",
            "Doug",
            "Doug Billings",
            "& Forever Wedding",
            "& Forever Wedding Chapel",
            "Mandalay Bay",
        )
    )
    # distinct: Vick, Alan, Doug Billings, Mandalay Bay
    assert out == {"researched": 9, "distinct": 4, "fragments": 5}


def test_account_keeps_unrelated_entities_apart():
    out = account(ents("Mandalay Bay", "Ghostbar", "Crazy Horse", "Pure"))
    assert out["distinct"] == 4 and out["fragments"] == 0


def test_account_short_form_folds_into_longer_only_when_real():
    # "Phil" folds under "Phil Wenneck"; "Ice" must NOT fold into a compound
    out = account(ents("Phil", "Phil Wenneck", "Ice", "Stu and Ice"))
    assert out["distinct"] == 2  # Phil Wenneck + Ice


def test_argued_scene_prefers_the_scene_the_body_names():
    flag = {
        "finding": "The brawl staged inside the Crazy Horse in S041 is the exposure.",
        "remedy": {"detail": "Rename the club."},
        "scene_ids": ["S012", "S041"],
    }
    assert _argued_scene(flag, ["S012", "S041"]) == "S041"
    # body names no anchor scene -> first anchor, unchanged behavior
    assert _argued_scene({"finding": "x", "remedy": {}}, ["S012", "S041"]) == "S012"


def test_binder_back_matter_moves_flagged_entities_out_of_cleared():
    from greenlight import binder

    record = {
        "entities": [
            {"entity_id": "E1", "surface": "Crazy Horse"},
            {"entity_id": "E2", "surface": "Ghostbar"},
        ],
        "flags": [
            {
                "flag_id": "F110",
                "entity_id": "E1",
                "scene_ids": ["S041"],
                "citations": [{"excerpt": "x"}],
                "severity": "HIGH",
                "category": "trade_libel_venue",
                "finding": "f",
                "remedy": {"action": "REPLACE", "detail": "d"},
                "agent": "clearance_counsel",
                "confidence": 0.9,
            }
        ],
        "cleared": {
            "clearance_counsel": [
                {"entity_id": "E1", "reasoning": "name cleared"},
                {"entity_id": "E2", "reasoning": "operating, backdrop only"},
            ]
        },
        "open_questions": {},
        "rejected_flags": [],
        "report": {},
    }
    back = binder._back_matter(record)
    cleared_texts = " ".join(c["text"] for c in back["cleared"])
    assert "Ghostbar" in cleared_texts
    assert "name cleared" not in cleared_texts  # E1 carries a finding
    assert any("carry findings" in c["text"] for c in back["cleared"] if c["desk"] == "note")

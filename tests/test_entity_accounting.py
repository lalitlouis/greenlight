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
    assert (out["researched"], out["distinct"], out["fragments"]) == (9, 4, 5)
    # "Doug" (E4) folds under "Doug Billings" (E5) so cleared displays merge
    assert out["fold"] == {"E4": "E5"}


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


# --- run-7 review: fragments must reconcile with the cleared list -----------


def test_fragment_ids_exposed_and_reconcile_with_distinct():
    out = account(
        ents("Alan", "Alan Mervish", "Stu and Alan", "& Forever Wedding", "1967 Cadillac Deville")
    )
    ids = {
        "E0": "Alan",
        "E1": "Alan Mervish",
        "E2": "Stu and Alan",
        "E3": "& Forever Wedding",
        "E4": "1967 Cadillac Deville",
    }
    # distinct = entities NOT in fragment_ids
    kept = [ids[e] for e in ids if e not in set(out["fragment_ids"])]
    assert out["distinct"] == len(kept)
    assert "Alan Mervish" in kept and "1967 Cadillac Deville" in kept
    # the short-form folds; the compound and truncation are fragments
    assert "E0" in out["fold"]  # Alan -> Alan Mervish


def test_digit_and_punctuation_starts_are_not_fragments():
    """`not s[0].isalpha()` wrongly folded real entities ('1967 Cadillac',
    '.357 MAGNUM') out of the headline count."""
    out = account(ents("1967 Cadillac Deville convertible", ".357 MAGNUM", "& Forever Wedding"))
    assert out["fragments"] == 1  # only the '&' truncation
    assert out["distinct"] == 2


def test_truncation_only_catches_leading_connectives():
    from greenlight.entity_accounting import _is_truncation

    assert _is_truncation("& Forever Wedding") and _is_truncation("and the crew")
    assert not _is_truncation(".357 MAGNUM") and not _is_truncation("1967 Cadillac")
    assert not _is_truncation("Mandalay Bay")


# ---- review 2026-09-01 (Worker 4A) ------------------------------------------


def test_fold_chains_resolve_to_the_canonical_entity():
    """Bob -> Bob's -> Bob's Burgers must fold to Bob's Burgers in one hop of
    lookup (single-hop folding dropped the short form's clearance entirely)."""
    out = account(ents("Bob", "Bob's", "Bob's Burgers"))
    assert out["fold"]["E0"] == "E2"
    assert out["fold"]["E1"] == "E2"
    assert out["distinct"] == 1


def test_polish_exposes_canonical_flagged_ids_and_body_flags():
    from greenlight.entity_accounting import polish_record

    rec = {
        "entities": [
            {"entity_id": "E0", "surface": "Bob"},
            {"entity_id": "E1", "surface": "Bob's Burgers"},
            {"entity_id": "E2", "surface": "Nighthawks"},
        ],
        "unexamined": [],
        "flags": [
            {"flag_id": "F1", "entity_id": "E0", "finding": "Nighthawks hangs crooked."},
        ],
        "cleared": {},
        "research": {},
        "entity_accounting": account(
            [
                {"entity_id": "E0", "surface": "Bob"},
                {"entity_id": "E1", "surface": "Bob's Burgers"},
                {"entity_id": "E2", "surface": "Nighthawks"},
            ]
        ),
    }
    polish_record(rec)
    acct = rec["entity_accounting"]
    assert acct["flagged_ids"] == ["E1"]  # E0 canonicalised through the fold
    assert acct["body_flagged_ids"] == ["E2"]


def test_items_examined_mirrors_the_web_row_count():
    from greenlight.entity_accounting import items_examined

    rec = {
        "entities": [
            {"entity_id": "E1", "surface": "Coors Light"},
            {"entity_id": "E2", "surface": "Thermos"},
            {"entity_id": "E3", "surface": "Stu and Alan"},
        ],
        "flags": [{"flag_id": "F1007", "entity_id": "E1", "agent": "clearance_counsel"}],
        "entity_accounting": {"fold": {}, "fragment_ids": ["E3"], "body_flagged_ids": []},
        "cleared": {
            "clearance_counsel": [
                {"entity_id": "E1", "reasoning": "Neutral use, cleared."},  # flagged -> elsewhere
                {"entity_id": "E2", "reasoning": "Generic term, no clearance required."},
                {"entity_id": "E3", "reasoning": "compound"},  # fragment -> dropped
                {"entity_id": "", "reasoning": "Axis sweep: no sexual content."},
                {"entity_id": "", "reasoning": "Language accounted for in F1007."},  # cited
            ],
            "territory_censor": [
                {"entity_id": "E2", "reasoning": "No cuts required for the Thermos."},
            ],
        },
        "open_questions": {
            "ratings_board": ["Alcohol scenes cleared at PG-13.", "Is the joint visible?"]
        },
    }
    out = items_examined(rec)
    # Thermos across two desks is ONE entity row; one script-level clearance
    # (the row citing F1007 is counted under the finding) plus one
    # determination-shaped open question
    assert out == {"entity_rows": 1, "script_level": 2, "flagged_elsewhere": 2}

"""The k-run matcher and agreement math — offline, synthetic runs."""

from __future__ import annotations

from greenlight.consistency import (
    chapman_estimate,
    krippendorff_alpha_binary,
    match_runs,
    normalize_surface,
    recall_bound,
)


def _rec(flags, entities):
    return {
        "flags": flags,
        "entities": [{"entity_id": k, "surface": v} for k, v in entities.items()],
    }


def test_matcher_survives_positional_entity_ids():
    """E-ids are per-run positional; the same person must match across runs."""
    r1 = _rec(
        [
            {
                "flag_id": "F101",
                "entity_id": "E001",
                "category": "sync_license",
                "scene_ids": ["S001"],
            }
        ],
        {"E001": "Gypsies, Tramps & Thieves"},
    )
    r2 = _rec(
        [
            {
                "flag_id": "F103",
                "entity_id": "E014",
                "category": "sync_license",
                "scene_ids": ["S001"],
            }
        ],
        {"E014": "Gypsies Tramps and Thieves"},  # different id, punctuation drift
    )
    m = match_runs([r1, r2])
    assert m["union_size"] == 1
    assert m["groups"][0]["agreement"] == "2/2"
    assert m["fuzzy_merges"] == 1


def test_disjoint_findings_stay_separate():
    r1 = _rec(
        [{"flag_id": "F1", "entity_id": "E001", "category": "sync_license", "scene_ids": ["S001"]}],
        {"E001": "Hallelujah"},
    )
    r2 = _rec(
        [{"flag_id": "F2", "entity_id": "E001", "category": "stunt_water", "scene_ids": ["S009"]}],
        {"E001": "Harbor climax"},
    )
    m = match_runs([r1, r2])
    assert m["union_size"] == 2
    assert all(g["agreement"] == "1/2" for g in m["groups"])


def test_entityless_findings_anchor_on_scene():
    f = {
        "flag_id": "F1",
        "entity_id": None,
        "category": "rating_language",
        "scene_ids": ["S003", "S006"],
    }
    m = match_runs([_rec([f], {}), _rec([dict(f, flag_id="F9")], {})])
    assert m["union_size"] == 1


def test_alpha_perfect_and_null():
    assert krippendorff_alpha_binary([[True, True], [True, True], [False, False]]) == 1.0
    a = krippendorff_alpha_binary([[True, False], [False, True], [True, False], [False, True]])
    assert a is not None and a < 0.1


def test_chapman_and_recall_bound():
    # 20 and 20 found, 16 overlap -> N-hat ~ 24.6
    assert 24 < chapman_estimate(20, 20, 16) < 26
    r1 = _rec(
        [
            {"flag_id": f"F{i}", "entity_id": f"E{i}", "category": "c", "scene_ids": ["S001"]}
            for i in range(4)
        ],
        {f"E{i}": f"unique entity {i}" for i in range(4)},
    )
    r2 = _rec(
        [
            {"flag_id": f"G{i}", "entity_id": f"X{i}", "category": "c", "scene_ids": ["S001"]}
            for i in (0, 1, 2)
        ],
        {f"X{i}": f"unique entity {i}" for i in (0, 1, 2)},
    )
    m = match_runs([r1, r2])
    rb = recall_bound(m)
    assert rb["union"] == 4
    assert 0.5 < rb["recall_upper_bound"] <= 1.0


def test_normalize_surface():
    assert normalize_surface("The 'Margaret Rose'!") == "margaret rose"

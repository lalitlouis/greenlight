"""apply_plan enforces the adjudicator's merge rules in code (2026-09-01 review,
B8): cross-desk merges, NO_ACTION-vs-actionable merges, sync/master pairs, and
out-of-vocabulary or protected-theory renames are refused with a note that names
only ids that still render. Pure functions, no ADK, no API."""

from __future__ import annotations

from greenlight.agents.adjudicator import apply_plan, category_admissible


def _flag(fid, agent, category, severity="MEDIUM", action="OBTAIN_LICENSE", scenes=("S001",)):
    return {
        "flag_id": fid,
        "agent": agent,
        "category": category,
        "severity": severity,
        "scene_ids": list(scenes),
        "citations": [{"url": f"https://x/{fid}", "excerpt": f"ex {fid}"}],
        "remedy": {"action": action, "detail": "d"},
        "finding": "f",
    }


def _merge(survivor, merged, category=None, severity="MEDIUM", rationale="dup"):
    a = {
        "surviving_flag_id": survivor,
        "merged_flag_ids": merged,
        "severity": severity,
        "rationale": rationale,
    }
    if category:
        a["category"] = category
    return a


def test_within_desk_merge_still_applies():
    flags = [
        _flag("F1001", "clearance_counsel", "trademark_use", scenes=("S001",)),
        _flag("F1002", "clearance_counsel", "trademark_use", scenes=("S002",)),
    ]
    out, notes = apply_plan(flags, {"merges": [_merge("F1001", ["F1002"])], "conflicts": []})
    assert [f["flag_id"] for f in out] == ["F1001"]
    assert out[0]["scene_ids"] == ["S001", "S002"]
    assert notes == ["F1001: absorbed F1002 (dup)"]


def test_cross_desk_merge_is_refused_and_both_render():
    flags = [
        _flag("F3001", "safety_underwriter", "stunt_pyro", "BLOCKER", "ADD_SPECIALIST"),
        _flag("F4001", "territory_censor", "territory_cn_supernatural", "HIGH", "CUT"),
    ]
    out, notes = apply_plan(flags, {"merges": [_merge("F3001", ["F4001"])], "conflicts": []})
    assert {f["flag_id"] for f in out} == {"F3001", "F4001"}
    assert len(notes) == 1
    assert notes[0].startswith("adjudication refused: merge of F4001 into F3001")
    assert "different desks" in notes[0]
    assert out[0]["severity"] == "BLOCKER" and out[0]["scene_ids"] == ["S001"]


def test_batch_agents_count_as_one_desk():
    flags = [
        _flag("F1001", "clearance_counsel__b1", "trademark_use"),
        _flag("F1002", "clearance_counsel__b2", "trademark_use"),
    ]
    out, notes = apply_plan(flags, {"merges": [_merge("F1001", ["F1002"])], "conflicts": []})
    assert [f["flag_id"] for f in out] == ["F1001"] and "refused" not in " ".join(notes)


def test_no_action_and_actionable_do_not_merge():
    """The F2008 class: a NO_ACTION note absorbing an actionable driver buried an
    R-rated violence finding under a MEDIUM 'fine as written' note."""
    flags = [
        _flag("F2001", "ratings_board", "rating_violence", "MEDIUM", "NO_ACTION"),
        _flag("F2002", "ratings_board", "rating_violence", "HIGH", "CUT", scenes=("S064",)),
    ]
    out, notes = apply_plan(flags, {"merges": [_merge("F2001", ["F2002"])], "conflicts": []})
    assert {f["flag_id"] for f in out} == {"F2001", "F2002"}
    assert any("NO_ACTION" in n and "refused" in n for n in notes)


def test_sync_and_master_never_merge():
    flags = [
        _flag("F1009", "clearance_counsel", "sync_license", "HIGH", scenes=("S004", "S011")),
        _flag("F1010", "clearance_counsel", "master_use_license", "HIGH", scenes=("S004", "S011")),
    ]
    out, notes = apply_plan(flags, {"merges": [_merge("F1009", ["F1010"])], "conflicts": []})
    assert {f["flag_id"] for f in out} == {"F1009", "F1010"}
    assert any("separate licen" in n for n in notes)


def test_rename_outside_vocabulary_is_refused():
    flags = [_flag("F1001", "clearance_counsel", "trademark_use")]
    plan = {"merges": [_merge("F1001", [], category="brand_stuff")], "conflicts": []}
    out, notes = apply_plan(flags, plan)
    assert out[0]["category"] == "trademark_use"
    assert notes == [
        "adjudication refused: rename of F1001 to brand_stuff — 'brand_stuff' is not in the "
        "clearance_counsel vocabulary (dup)"
    ]


def test_protected_theory_never_collapses():
    flags = [_flag("F1001", "clearance_counsel", "defamation_false_light", "HIGH")]
    action = _merge("F1001", [], category="right_of_publicity", severity="HIGH")
    plan = {"merges": [action], "conflicts": []}
    out, notes = apply_plan(flags, plan)
    assert out[0]["category"] == "defamation_false_light"
    assert notes and "distinct legal theory" in notes[0]


def test_admissible_rename_applies_and_is_noted():
    flags = [_flag("F1001", "clearance_counsel", "trademark_use")]
    plan = {"merges": [_merge("F1001", [], category="trademark_disparagement")], "conflicts": []}
    out, notes = apply_plan(flags, plan)
    assert out[0]["category"] == "trademark_disparagement"
    assert notes == ["F1001: category normalized to trademark_disparagement (dup)"]


def test_category_admissible_patterns():
    assert category_admissible("territory_censor", "territory_cn_supernatural")
    assert not category_admissible("territory_censor", "territory_fr_supernatural")
    assert not category_admissible("territory_censor", "territory_cn_ghosts")
    assert category_admissible("ratings_board", "rating_language")
    assert category_admissible("ratings_board", "rating_nudity")
    assert not category_admissible("ratings_board", "language")
    assert category_admissible("safety_underwriter", "stunt_pyro")
    assert not category_admissible("safety_underwriter", "pyro")


def test_refusal_notes_name_only_rendered_ids():
    flags = [
        _flag("F1001", "clearance_counsel", "trademark_use"),
        _flag("F3001", "safety_underwriter", "stunt_pyro", action="ADD_SPECIALIST"),
    ]
    plan = {"merges": [_merge("F1001", ["F3001", "F9999"])], "conflicts": []}
    out, notes = apply_plan(flags, plan)
    rendered = {f["flag_id"] for f in out}
    import re

    for n in notes:
        assert set(re.findall(r"\bF\d{4}\b", n)) <= rendered

"""Deterministic pre-pass: sweep, triage delta, worklist shaping."""

from __future__ import annotations

from greenlight.prepass import as_worklist_items, delta_against_triage, sweep


def _scene(sid, action="", lines=()):
    return {"scene_id": sid, "action": action, "dialogue": [{"line": ln} for ln in lines]}


def test_sweep_finds_privacy_vectors_and_names():
    scenes = [
        _scene("S001", "MARA answers the PAY PHONE. The number 212-664-7665 is scrawled on it.",
               ["Call me at bubba@harborbar.com, or check www.harborbar.com"]),
        _scene("S002", "A poster for Blue Harbor Session hangs by the door.",
               ['She hums "Gypsies, Tramps and Thieves" under her breath.']),
    ]
    got = {(c["surface"], c["kind"]) for c in sweep(scenes)}
    assert ("212-664-7665", "PHONE_NUMBER") in got
    assert ("bubba@harborbar.com", "EMAIL") in got
    assert ("www.harborbar.com", "URL") in got
    assert any(k == "QUOTED_TITLE" and "Gypsies" in s for s, k in got)
    assert any(k == "PROPER_NOUN" and "Blue Harbor" in s for s, k in got)


def test_sweep_is_deterministic():
    scenes = [_scene("S001", "DANNY nods at the Iron Anchor Tavern sign.")]
    assert sweep(scenes) == sweep(scenes)


def test_delta_respects_triage_coverage_but_keeps_privacy():
    cands = [
        {"surface": "Iron Anchor Tavern", "kind": "PROPER_NOUN", "scene_ids": ["S001"]},
        {"surface": "212-664-7665", "kind": "PHONE_NUMBER", "scene_ids": ["S001"]},
    ]
    ents = [{"surface": "THE IRON ANCHOR TAVERN"}]
    d = delta_against_triage(cands, ents)
    kinds = [c["kind"] for c in d]
    assert "PHONE_NUMBER" in kinds  # privacy vectors always survive
    assert "PROPER_NOUN" not in kinds  # triage already had the tavern


def test_worklist_items_are_low_priority_and_labeled():
    d = [{"surface": "555-0100", "kind": "PHONE_NUMBER", "scene_ids": ["S003"]}]
    (item,) = as_worklist_items(d, 1)
    assert item["entity_id"] == "P001"
    assert item["type"] == "PRIVACY"
    assert item["prominence"] == "BACKGROUND"
    assert "PRE-PASS" in item["context"]

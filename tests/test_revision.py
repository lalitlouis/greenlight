"""Findings diff across drafts — the revision product's core."""

from __future__ import annotations

import pytest

from greenlight.revision import diff_records


def _rec(flags, entities, sha="aaa"):
    return {
        "flags": flags,
        "entities": [{"entity_id": k, "surface": v} for k, v in entities.items()],
        "draft": {"sha256": sha, "pages": 100, "scene_count": 50},
    }


def _flag(fid, eid, cat, sev="MEDIUM", finding="x"):
    return {
        "flag_id": fid,
        "entity_id": eid,
        "category": cat,
        "severity": sev,
        "finding": finding,
        "scene_ids": ["S001"],
        "citations": [{}],
    }


def test_diff_classifies_new_not_reproduced_unchanged_and_severity():
    old = _rec(
        [
            _flag("F101", "E001", "sync_license"),
            _flag("F102", "E002", "trademark_use"),
            _flag("F103", "E003", "stunt_water", sev="HIGH"),
        ],
        {"E001": "Hallelujah", "E002": "Coors Light", "E003": "Harbor climax"},
        sha="old",
    )
    new = _rec(
        [
            _flag("F201", "E010", "sync_license"),  # same song, new ids
            _flag("F202", "E011", "stunt_water", sev="MEDIUM"),  # severity moved
            _flag("F203", "E012", "defamation_false_light"),  # new person
        ],
        {"E010": "Hallelujah", "E011": "Harbor Climax", "E012": "Judge Stogel"},
        sha="new",
    )
    d = diff_records(old, new)
    assert [f["flag_id"] for f in d["new"]] == ["F203"]
    assert [f["flag_id"] for f in d["not_reproduced"]] == ["F102"]
    assert d["resolved"] == []
    assert [f["flag_id"] for f in d["unchanged"]] == ["F201"]
    assert d["severity_changed"][0]["was_severity"] == "HIGH"
    assert d["drafts"]["same_text"] is False
    assert "1 new, 1 not reproduced" in d["summary"]


def test_same_text_flagged_as_variance_not_changes():
    r = _rec([_flag("F1", "E1", "c")], {"E1": "Thing"}, sha="same")
    d = diff_records(r, _rec([_flag("F2", "E9", "c")], {"E9": "Thing"}, sha="same"))
    assert d["drafts"]["same_text"] is True
    assert len(d["unchanged"]) == 1


@pytest.mark.parametrize("sha", ["same", "edited", ""])
@pytest.mark.parametrize("failed", [False, True])
def test_disappearing_finding_is_never_evidence_of_resolution(sha, failed):
    old = _rec([_flag("F1", "E1", "sync_license")], {"E1": "A song"}, sha="same")
    new = _rec([], {}, sha=sha)
    if failed:
        new["error"] = "Verifier unavailable"
        new["desks_incomplete"] = ["clearance_counsel"]
    diff = diff_records(old, new)
    assert diff["resolved"] == []
    assert [f["flag_id"] for f in diff["not_reproduced"]] == ["F1"]
    assert "resolved" not in diff["summary"]


def test_inserted_scene_does_not_flip_an_unchanged_entityless_finding():
    old = _rec([dict(_flag("F1", None, "stunt_water"), scene_ids=["S009"])], {}, sha="a")
    old["scene_meta"] = {"S009": {"heading": "EXT. HARBOR - NIGHT"}}
    new = _rec([dict(_flag("F2", None, "stunt_water"), scene_ids=["S010"])], {}, sha="b")
    new["scene_meta"] = {"S010": {"heading": "EXT. HARBOR - NIGHT"}}
    d = diff_records(old, new)
    assert d["new"] == [] and d["resolved"] == []
    assert [f["flag_id"] for f in d["unchanged"]] == ["F2"]

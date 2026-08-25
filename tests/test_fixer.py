"""Patch validation is the safety property: only deterministic patches survive."""

from greenlight.fixer import validate_patches

SCENES = {"S001": "MARA\nHe was a glorious, impossible man.\n\nShe pours whiskey."}


def patch(scene="S001", find="glorious, impossible man", replace="glorious, difficult man"):
    return {"scene_id": scene, "find": find, "replace": replace, "rationale": "r"}


def test_valid_patch_survives():
    assert len(validate_patches([patch()], SCENES)) == 1


def test_unknown_scene_dropped():
    assert validate_patches([patch(scene="S099")], SCENES) == []


def test_nonunique_find_dropped():
    scenes = {"S001": "the man and the man"}
    assert validate_patches([patch(find="the man", replace="a man")], scenes) == []


def test_no_op_and_empty_dropped():
    assert validate_patches([patch(replace="glorious, impossible man")], SCENES) == []
    assert validate_patches([patch(find="  ")], SCENES) == []


def test_missing_text_dropped():
    assert validate_patches([patch(find="not in the scene")], SCENES) == []

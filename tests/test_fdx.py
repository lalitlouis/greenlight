"""FDX intake: native structure -> Fountain -> Scene[], numbers preserved."""

from __future__ import annotations

import pytest

from greenlight.fdx import FdxError, fdx_to_fountain
from greenlight.parser import parse_fountain
from greenlight.pdf import screenplay_text
from greenlight.pipeline import _draft_identity

FDX = """<?xml version="1.0" encoding="UTF-8"?>
<FinalDraft DocumentType="Script" Template="No" Version="5">
<Content>
<Paragraph Type="Scene Heading" Number="12"><Text>INT. HARBOR BAR - NIGHT</Text></Paragraph>
<Paragraph Type="Action"><Text>MARA wipes the counter.</Text></Paragraph>
<Paragraph Type="Character"><Text>Mara</Text></Paragraph>
<Paragraph Type="Dialogue"><Text>We're closed.</Text></Paragraph>
<Paragraph Type="Scene Heading" Number="12A"><Text>EXT. HARBOR - CONTINUOUS</Text></Paragraph>
<Paragraph Type="Action"><Text>Fog rolls in.</Text></Paragraph>
</Content>
</FinalDraft>"""


def test_fdx_carries_locked_scene_numbers() -> None:
    _, scenes = parse_fountain(screenplay_text("blue_draft.fdx", FDX.encode()))
    assert [s.get("number") for s in scenes] == ["12", "12A"]
    assert scenes[0]["scene_id"] == "S001"  # internal id stays stable
    assert scenes[0]["dialogue"][0]["character"] == "MARA"


def test_invalid_fdx_is_rejected_with_guidance() -> None:
    with pytest.raises(FdxError, match="Final Draft"):
        fdx_to_fountain(b"<html>not a screenplay</html>")


def test_fdx_without_scenes_is_rejected() -> None:
    empty = b'<?xml version="1.0"?><FinalDraft><Content><Paragraph Type="Action"><Text>hi</Text></Paragraph></Content></FinalDraft>'
    with pytest.raises(FdxError, match="scene headings"):
        fdx_to_fountain(empty)


def test_fountain_hash_numbers_parse() -> None:
    src = "Title: T\n\nINT. BAR - DAY #45#\n\nA quiet room.\n\nEXT. DOCK - DAY\n\nWaves.\n"
    _, scenes = parse_fountain(src)
    assert scenes[0].get("number") == "45"
    assert scenes[0]["heading"] == "INT. BAR - DAY"
    assert "number" not in scenes[1]


def test_draft_identity_provenance() -> None:
    src = "INT. BAR - DAY #1#\n\nHello.\n"
    meta, scenes = parse_fountain(src)
    d = _draft_identity(src, meta, scenes, "T")
    assert d["scene_numbers"] == "script"
    assert len(d["sha256"]) == 64
    assert d["scene_count"] == 1

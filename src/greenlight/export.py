"""Revised-script export: accepted fix patches applied to the original source,
downloadable as Fountain (revision stars) or Final Draft .fdx (revision marks).

Everything here is deterministic. Patches are re-validated server-side with the
same rule the fixer uses — the find text must occur exactly once inside its
scene — so a stale or tampered patch is dropped, never mis-applied.
"""

from __future__ import annotations

import difflib
import re
from typing import Any
from xml.sax.saxutils import escape

from greenlight import parser

MAX_PATCHES = 20
MAX_CUE_CHARS = 40  # character cues longer than this are prose, not names

_TITLE_KEY = re.compile(r"^[A-Za-z][A-Za-z ]*:(\s|$)")
_TRANSITION = re.compile(r"(TO:|FADE IN:|FADE OUT\.?|CUT TO BLACK\.?)\s*$")
_CHARACTER = re.compile(r"^[A-Z][A-Z0-9 .'\-]*(\s*\((V\.O\.|O\.S\.|CONT'D)\))?$")


def apply_patches(
    source: str, patches: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Apply scene-scoped find→replace patches. Returns (revised_source,
    applied, skipped_reasons). Re-parses between patches so spans stay honest."""
    applied: list[dict[str, Any]] = []
    skipped: list[str] = []
    text = source
    for p in patches[:MAX_PATCHES]:
        sid = str(p.get("scene_id", ""))
        find = str(p.get("find", ""))
        replace = str(p.get("replace", ""))
        if not find.strip() or find == replace:
            skipped.append(f"{sid}: empty or no-op patch")
            continue
        _, scenes = parser.parse_fountain(text)
        scene = next((s for s in scenes if s["scene_id"] == sid), None)
        if scene is None:
            skipped.append(f"{sid}: unknown scene")
            continue
        a, b = scene["raw_span"]
        segment = text[a:b]
        if segment.count(find) != 1:
            skipped.append(f"{sid}: find text not unique in scene ({segment.count(find)} hits)")
            continue
        text = text[:a] + segment.replace(find, replace, 1) + text[b:]
        applied.append(p)
    return text, applied, skipped


def changed_lines(original: str, revised: str) -> set[int]:
    """Indices (into revised.splitlines()) of lines that differ from the original."""
    o, r = original.splitlines(), revised.splitlines()
    changed: set[int] = set()
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(None, o, r).get_opcodes():
        if tag != "equal":
            changed.update(range(j1, j2))
    return changed


def to_fountain(revised: str, changed: set[int]) -> str:
    """The revised script with the industry convention: a star on changed lines."""
    out = []
    for i, line in enumerate(revised.splitlines()):
        out.append(f"{line} *" if i in changed and line.strip() else line)
    return "\n".join(out) + "\n"


def _classify(lines: list[str]) -> list[tuple[str, str, int]]:
    """(paragraph_type, text, line_index) per non-empty line, standard Fountain
    semantics: heading / character / parenthetical / dialogue / transition / action."""
    paras: list[tuple[str, str, int]] = []
    in_title = True
    in_dialogue = False
    for i, raw in enumerate(lines):
        line = raw.rstrip()
        stripped = line.strip()
        if in_title:
            if not stripped:
                continue
            if _TITLE_KEY.match(stripped) and not parser.is_scene_heading(stripped):
                continue  # title-page keys carry over to the FDX TitlePage-less body
            in_title = False
        if not stripped:
            in_dialogue = False
            continue
        if parser.is_scene_heading(stripped):
            paras.append(("Scene Heading", stripped, i))
            in_dialogue = False
        elif _TRANSITION.search(stripped) and stripped == stripped.upper():
            paras.append(("Transition", stripped, i))
            in_dialogue = False
        elif in_dialogue and stripped.startswith("(") and stripped.endswith(")"):
            paras.append(("Parenthetical", stripped, i))
        elif in_dialogue:
            paras.append(("Dialogue", stripped, i))
        elif (
            _CHARACTER.match(stripped)
            and len(stripped) <= MAX_CUE_CHARS
            and i + 1 < len(lines)
            and lines[i + 1].strip()
        ):
            paras.append(("Character", stripped, i))
            in_dialogue = True
        else:
            paras.append(("Action", stripped, i))
    return paras


def to_fdx(revised: str, changed: set[int], title: str) -> str:
    """A minimal, valid Final Draft document. Changed paragraphs carry
    RevisionID 2, defined as the blue 'ScriptRisk Revision' set — Final Draft
    renders these as revision-marked (colored-page) material on import."""
    lines = revised.splitlines()
    body: list[str] = []
    for ptype, text, idx in _classify(lines):
        rev = ' RevisionID="2"' if idx in changed else ""
        body.append(f'    <Paragraph Type="{ptype}"><Text{rev}>{escape(text)}</Text></Paragraph>')
    content = "\n".join(body)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<FinalDraft DocumentType="Script" Template="No" Version="5">
  <Content>
{content}
  </Content>
  <Revisions ActiveRevision="2">
    <Revision Color="#000000" ID="1" Mark="" Name="{escape(title)} — base" Style=""/>
    <Revision Color="#0000FF" ID="2" Mark="*" Name="ScriptRisk Revision"
              PageColor="#CCE5FF" Style="Bold"/>
  </Revisions>
</FinalDraft>
"""

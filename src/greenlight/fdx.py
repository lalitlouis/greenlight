"""Final Draft (.fdx) intake: native structure to Fountain-shaped text.

FDX is the industry delivery standard and the one input whose XML hands us
structure for free — scene boundaries, element types per paragraph, and the
locked scene numbers every production department cross-references. This
adapter converts to Fountain so everything downstream keeps speaking one
format, and embeds the script's own scene numbers with Fountain's #42#
syntax so the parser carries them (never invents its own when they exist).

Third-party FDX is validated, not trusted: Final Draft's own knowledge base
warns that other tools' .fdx output may not be well-formed. A file that does
not parse, or parses without a single scene heading, raises FdxError with a
message the upload path can show the user.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

_DATE_LINE_MAX = 40  # a title-page line short enough to plausibly be a draft date


class FdxError(ValueError):
    """The file claims to be FDX but does not carry usable Final Draft XML."""


def looks_like_fdx(filename: str, data: bytes) -> bool:
    head = data[:512].lstrip()
    return filename.lower().endswith(".fdx") or b"<FinalDraft" in head


def _text_of(paragraph: ET.Element) -> str:
    return "".join(t.text or "" for t in paragraph.iter("Text")).strip()


def fdx_to_fountain(data: bytes) -> str:
    """FDX bytes -> Fountain text, scene numbers preserved as #N# suffixes."""
    try:
        root = ET.fromstring(data.decode("utf-8-sig", errors="replace"))
    except ET.ParseError as exc:
        raise FdxError(
            "This .fdx file is not valid Final Draft XML. If it came from another "
            "app, export it again as PDF or Fountain and upload that instead."
        ) from exc
    if root.tag != "FinalDraft":
        raise FdxError("Not a Final Draft document (missing <FinalDraft> root).")

    out: list[str] = []
    title = _title_page(root)
    if title:
        out.append(title)

    content = root.find("Content")
    if content is None:
        raise FdxError("Final Draft file has no <Content> element.")

    scene_count = 0
    for para in content.iter("Paragraph"):
        ptype = (para.get("Type") or "").strip()
        text = _text_of(para)
        if not text and ptype != "Scene Heading":
            continue
        if ptype == "Scene Heading":
            scene_count += 1
            out.extend(["", _heading_line(para, text), ""])
        else:
            out.extend(_body_lines(ptype, text))

    if scene_count == 0:
        raise FdxError(
            "No scene headings found in this .fdx — it may be a title page, an "
            "outline, or a malformed export. Export as PDF or Fountain and retry."
        )
    return "\n".join(out).strip() + "\n"


def _heading_line(para: ET.Element, text: str) -> str:
    number = (para.get("Number") or "").strip()
    heading = text if text else "INT. UNTITLED SCENE"
    # Force the parser to see a heading even for nonstandard sluglines.
    if not heading.upper().startswith(("INT", "EXT", "I/E", "EST")):
        heading = "." + heading
    return f"{heading} #{number}#" if number else heading


def _body_lines(ptype: str, text: str) -> list[str]:
    if ptype == "Character":
        return ["", text.upper()]
    if ptype == "Parenthetical":
        return [text if text.startswith("(") else f"({text})"]
    if ptype == "Dialogue":
        return [text]
    if ptype == "Transition":
        return ["", f"> {text}" if not text.endswith(":") else text, ""]
    return ["", text]  # Action, General, Shot, anything else — action-shaped


def _title_page(root: ET.Element) -> str:
    tp = root.find(".//TitlePage")
    if tp is None:
        return ""
    lines = [_text_of(p) for p in tp.iter("Paragraph")]
    lines = [ln for ln in lines if ln]
    if not lines:
        return ""
    meta = [f"Title: {lines[0]}"]
    for ln in lines[1:4]:
        low = ln.lower()
        if low.startswith(("by", "written by")):
            meta.append(f"Author: {ln.split('by', 1)[-1].strip() or ln}")
        elif any(ch.isdigit() for ch in ln) and len(ln) < _DATE_LINE_MAX:
            meta.append(f"Draft date: {ln}")
    return "\n".join(meta) + "\n"

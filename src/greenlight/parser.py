"""Deterministic Fountain screenplay parser. No model anywhere near this file.

A hallucinated scene number breaks every anchor downstream, so parsing is plain
Python: screenplay text in, Scene[] out, each validated against scene.schema.json.

raw_span is [start, end) char offsets into the ORIGINAL source text — the marked-up
script view depends on these being exact, so scenes are sliced, never re-assembled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from greenlight.contracts import validate

# A scene heading: INT./EXT. variants (period, colon, or space form), optionally
# carrying shooting-script scene numbers ("12 INT. BAR - NIGHT 12"), or a forced
# heading starting with a period (which must then read like a slugline, not prose —
# OCR of a sentence that lost its first word also starts with a period).
_HEADING_RE = re.compile(
    r"^(?:\d+[A-Z]?\s+)?(?:\.(?=[A-Z0-9])|(?:INT\.?/EXT|EXT\.?/INT|INT|EXT|EST|I/E)[.:\s])",
    re.IGNORECASE,
)
_SCENE_NUM_PREFIX = re.compile(r"^\d+[A-Z]?\s+")
_SCENE_NUM_SUFFIX = re.compile(r"\s+\d+[A-Z]?$")


def _is_heading(stripped: str) -> bool:
    if not _HEADING_RE.match(stripped):
        return False
    if stripped.startswith("."):  # forced heading: sluglines shout, prose does not
        letters = [c for c in stripped if c.isalpha()]
        if not letters or sum(c.isupper() for c in letters) / len(letters) < _FORCED_HEADING_UPPER:
            return False
    return True


def is_scene_heading(stripped: str) -> bool:
    """Public form of the heading test — the exporter classifies lines with it."""
    return _is_heading(stripped)


_TIME_WORDS = {
    "DAY",
    "NIGHT",
    "DAWN",
    "DUSK",
    "MORNING",
    "AFTERNOON",
    "EVENING",
    "SUNSET",
    "SUNRISE",
    "CONTINUOUS",
    "LATER",
    "MOMENTS LATER",
    "SAME",
    "SAME TIME",
    "THE WAKE",
}
_CUE_EXTENSION_RE = re.compile(r"\s*\((?:CONT'D|O\.S\.|O\.C\.|V\.O\.|OFF)\.?\)\s*$", re.IGNORECASE)
_TRANSITION_RE = re.compile(
    r"^(?:[A-Z ]+TO:|FADE (?:IN|OUT)[.:]?|SMASH CUT[.:]?|CUT TO BLACK[.:]?)$"
)

# Crude but deterministic page model: a formatted screenplay page is ~55 lines;
# action wraps at ~60 chars, dialogue at ~35.
_LINES_PER_PAGE = 55
_MAX_CUE_LEN = 40
_FORCED_HEADING_UPPER = 0.8


def _formatted_lines(text_line: str, kind: str) -> int:
    width = 35 if kind == "dialogue" else 60
    stripped = text_line.strip()
    if not stripped:
        return 1
    return max(1, -(-len(stripped) // width))  # ceil division


@dataclass
class _SceneAccumulator:
    heading: str
    start: int
    action_parts: list[str] = field(default_factory=list)
    dialogue: list[dict[str, str]] = field(default_factory=list)
    characters: list[str] = field(default_factory=list)
    line_count: int = 1  # the heading line itself


def _split_heading(heading: str) -> tuple[str, str, str]:
    """'INT./EXT. MARGARET ROSE - WHEELHOUSE - NIGHT - CONTINUOUS'
    -> ('INT/EXT', 'MARGARET ROSE - WHEELHOUSE', 'NIGHT - CONTINUOUS').
    Also handles '12 INT. BAR - NIGHT 12' and 'INT: BEDROOM. MORNING'."""
    text = _SCENE_NUM_SUFFIX.sub("", _SCENE_NUM_PREFIX.sub("", heading)).lstrip(".").strip()
    upper = text.upper()
    if upper.startswith(("INT./EXT", "INT/EXT", "EXT./INT", "EXT/INT", "I/E")):
        int_ext = "INT/EXT"
    elif upper.startswith("INT"):
        int_ext = "INT"
    elif upper.startswith(("EXT", "EST")):
        int_ext = "EXT"
    else:
        int_ext = "UNKNOWN"

    body = re.sub(
        r"^(?:INT\.?/EXT|EXT\.?/INT|INT|EXT|EST|I/E)[.:\s]+", "", text, flags=re.IGNORECASE
    )
    if " - " in body:
        segments = [s.strip() for s in body.split(" - ") if s.strip()]
        time_segments: list[str] = []
        while segments and segments[-1].upper() in _TIME_WORDS:
            time_segments.insert(0, segments.pop())
        location = " - ".join(segments) if segments else body.strip()
        time_of_day = " - ".join(time_segments) if time_segments else "UNKNOWN"
    elif ". " in body:  # 'BEDROOM. EARLY-MORNING HOURS' — dot-separated slug style
        location, _, time_of_day = body.rpartition(". ")
        location = location.strip().rstrip(".")
        time_of_day = time_of_day.strip() or "UNKNOWN"
    else:
        location, time_of_day = body.strip().rstrip("."), "UNKNOWN"
    return int_ext, location, time_of_day


def _is_cue(line: str, next_line: str | None) -> bool:
    """A character cue is a short all-caps line immediately followed by speech."""
    stripped = line.strip()
    if not stripped or next_line is None or not next_line.strip():
        return False
    if len(stripped) > _MAX_CUE_LEN or stripped.endswith(":") or _is_heading(stripped):
        return False
    if _TRANSITION_RE.match(stripped):
        return False
    bare = _CUE_EXTENSION_RE.sub("", stripped)
    letters = [c for c in bare if c.isalpha()]
    return bool(letters) and bare == bare.upper() and not bare.endswith(".")


def strip_title_page(text: str) -> tuple[dict[str, str], int]:
    """Parse the Fountain title page. Returns (metadata, offset of body start)."""
    meta: dict[str, str] = {}
    offset = 0
    lines = text.split("\n")
    key = None
    pos = 0
    for line in lines:
        line_end = pos + len(line) + 1
        if re.match(r"^[A-Za-z][A-Za-z ]*:", line):
            key, _, value = line.partition(":")
            key = key.strip().lower()
            meta[key] = value.strip()
        elif line.startswith(("   ", "\t")) and key:
            meta[key] = (meta[key] + "\n" + line.strip()).strip()
        elif not line.strip():
            if meta:
                offset = line_end
        else:
            break
        pos = line_end
    return (meta, offset) if meta else ({}, 0)


_FRONT_MARKER_RE = re.compile(
    r"(?im)\b(written by|screenplay by|story by|draft|revis\w*|copyright|all rights)\b"
    r"|^[A-Za-z][A-Za-z ]{0,20}:"
)
_MAX_FRONT_SEGMENTS = 3  # title + at most a cast/notes page or two
_FRONT_MAX_LINES = 12
_FRONT_TITLE_MAX_CHARS = 40


def _looks_like_front_matter(segment: str) -> bool:
    lines = [ln.strip() for ln in segment.split("\n") if ln.strip()]
    if not lines:
        return True  # an empty leading page is padding, not page 1
    for ln in lines:
        if _is_heading(ln) and not _TRANSITION_RE.match(ln):
            return False
        if _TRANSITION_RE.match(ln) or ln.upper().startswith("FADE IN"):
            return False  # transitions mean the movie has started
    if _FRONT_MARKER_RE.search("\n".join(lines)):
        return True
    # a short all-caps opening line reads as a display title page
    first = lines[0]
    return (
        len(lines) <= _FRONT_MAX_LINES
        and first == first.upper()
        and len(first) <= _FRONT_TITLE_MAX_CHARS
    )


def _front_matter_feeds(text: str) -> int:
    """Form feeds that belong to front matter, i.e. precede printed page 1.
    Detected STRUCTURALLY from the leading feed-delimited segments — a real PDF
    title page ('THE HANGOVER / Written by / ...') carries no Fountain metadata
    at all, so any meta-based guard silently never fires (run 5: the fourth
    consecutive review to flag every scene page running exactly +1)."""
    if "\f" not in text:
        return 0
    segments = text.split("\f")
    front = 0
    for seg in segments[: min(_MAX_FRONT_SEGMENTS, len(segments) - 1)]:
        if _looks_like_front_matter(seg):
            front += 1
        else:
            break
    return front


def printed_page_count(text: str) -> int | None:
    """Total printed pages when the source preserves form feeds; None otherwise.
    max(scene page) undercounts — script pages after the last scene heading are
    still pages (the header read 110 pp against a real 111)."""
    if "\f" not in text:
        return None
    return max(1, len(text.split("\f")) - _front_matter_feeds(text))


_SCENE_NUMBER_RE = __import__("re").compile(r"\s*#([A-Za-z0-9.\-]+)#\s*$")


def _extract_scene_number(heading: str) -> tuple[str, str]:
    """Fountain scene-number syntax: "INT. HOUSE - DAY #42A#" -> ("INT. HOUSE - DAY", "42A").
    Locked production numbers are a shared coordinate system — carry them, never invent."""
    m = _SCENE_NUMBER_RE.search(heading)
    if not m:
        return heading, ""
    return heading[: m.start()].rstrip(), m.group(1)


def parse_fountain(  # noqa: PLR0912, PLR0915 - one continuous scan loop
    text: str,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Parse Fountain source into (title_metadata, Scene[]).

    Every scene dict validates against scene.schema.json before it is returned.
    """
    meta, body_start = strip_title_page(text)

    # Locate scene heading line starts, as offsets into the original text.
    heading_positions: list[tuple[int, str]] = []
    pos = body_start
    for line in text[body_start:].split("\n"):
        stripped = line.strip()
        if _is_heading(stripped) and not _TRANSITION_RE.match(stripped):
            heading_positions.append((pos, stripped))
        pos += len(line) + 1

    scenes: list[dict[str, Any]] = []
    cumulative_lines = 0.0
    # Real pagination when the source preserves page breaks (PDF form feeds):
    # a scene's page is 1 + feeds before its heading. Fountain text without
    # feeds falls back to the deterministic ~55-line model.
    has_feeds = "\f" in text
    # Printed screenplay pages start AFTER front matter: subtract the feeds
    # consumed by the title page so scene pages match the script's own printed
    # numbers (the raw index ran uniformly +1 on a real 111-page script).
    front_feeds = _front_matter_feeds(text) if has_feeds else 0

    for i, (start, heading) in enumerate(heading_positions):
        end = heading_positions[i + 1][0] if i + 1 < len(heading_positions) else len(text)
        chunk = text[start:end]
        acc = _SceneAccumulator(heading=heading, start=start)

        lines = chunk.split("\n")[1:]  # skip the heading line itself
        j = 0
        while j < len(lines):
            line = lines[j]
            stripped = line.strip()
            next_line = lines[j + 1] if j + 1 < len(lines) else None
            if not stripped:
                j += 1
                continue
            if _TRANSITION_RE.match(stripped):
                acc.line_count += 1
                j += 1
                continue
            if _is_cue(line, next_line):
                character = _CUE_EXTENSION_RE.sub("", stripped).strip()
                if character not in acc.characters:
                    acc.characters.append(character)
                acc.line_count += 1
                j += 1
                parenthetical = ""
                speech: list[str] = []
                while j < len(lines) and lines[j].strip():
                    dline = lines[j].strip()
                    if dline.startswith("(") and dline.endswith(")") and not speech:
                        parenthetical = dline
                    else:
                        speech.append(dline)
                    acc.line_count += _formatted_lines(dline, "dialogue")
                    j += 1
                entry: dict[str, str] = {"character": character, "line": " ".join(speech)}
                if parenthetical:
                    entry["parenthetical"] = parenthetical
                acc.dialogue.append(entry)
                continue
            acc.action_parts.append(stripped)
            acc.line_count += _formatted_lines(stripped, "action")
            j += 1

        if has_feeds:
            # count through start+1: an extractor may attach the feed to the
            # heading's own line ("\fINT. ..."), where the page's leading feed
            # sits AT start rather than before it
            page = max(1, 1 + text.count("\f", 0, start + 1) - front_feeds)
        else:
            page = 1 + int(cumulative_lines // _LINES_PER_PAGE)
        cumulative_lines += acc.line_count + 1  # + blank line before next heading

        clean_heading, scene_number = _extract_scene_number(heading)
        int_ext, location, time_of_day = _split_heading(clean_heading)
        scene = {
            "scene_id": f"S{i + 1:03d}",
            "page": page,
            "heading": clean_heading,
            "int_ext": int_ext,
            "location": location,
            "time_of_day": time_of_day,
            "action": "\n\n".join(acc.action_parts),
            "dialogue": acc.dialogue,
            "characters": acc.characters,
            "raw_span": [start, end],
        }
        scene |= {"number": scene_number} if scene_number else {}
        scenes.append(validate("scene", scene))

    return meta, scenes


def annotated_script(text: str, scenes: list[dict[str, Any]]) -> str:
    """The script with [scene_id] markers on each heading — what Triage reads,
    so the scene ids it assigns to entities are the parser's ids, not inventions."""
    out: list[str] = []
    for scene in scenes:
        start, end = scene["raw_span"]
        out.append(f"[{scene['scene_id']}] {text[start:end].rstrip()}")
    return "\n\n".join(out)


def draft_identity(
    source: str, meta: dict[str, Any], scenes: list[dict[str, Any]], title: str
) -> dict[str, Any]:
    """Chain of custody: a clearance report is only valid for the exact draft it
    ran against. Hash, size, page count, and whether the scene numbers are the
    script's own locked numbers or our generated coordinates."""
    import hashlib

    numbered = sum(1 for sc in scenes if sc.get("number"))
    return {
        "title": title,
        "draft_date": meta.get("draft date") or meta.get("draft_date") or "",
        "revision_label": meta.get("revision") or "",
        "sha256": hashlib.sha256(source.encode()).hexdigest(),
        "bytes": len(source.encode()),
        "pages": max((sc.get("page", 1) for sc in scenes), default=1),
        "scene_count": len(scenes),
        "scene_numbers": "script" if numbered >= max(1, len(scenes) // 2) else "generated",
    }

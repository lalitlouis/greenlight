"""Conservative display-text matching that returns an unchanged source substring.

This is not semantic fuzzy matching or a Markdown renderer. Unsupported/truncated
markup stays literal. Non-whitespace characters, punctuation, case and order stay fixed.
"""

from __future__ import annotations

import re

_MIN_SPACING_WORDS = 4


def _display_chars(source: str) -> list[tuple[str, int, int]]:
    # Keep source offsets through each deletion and whitespace collapse. Only
    # complete inline HTTP(S) links are supported; images and nested labels stay
    # literal. Link destinations are attribution, not visible operative text.
    keep = [True] * len(source)
    links = re.compile(r'(?<!!)\[([^\[\]\n]+)\]\(https?://[^\s()]+(?:\s+"[^"\n]*")?\)')
    for match in links.finditer(source):
        start, end = match.span(1)
        keep[match.start() : start] = [False] * (start - match.start())
        keep[end : match.end()] = [False] * (match.end() - end)
    # Paired emphasis only, at word boundaries; never remove underscores inside
    # identifiers, arithmetic asterisks or unmatched/truncated delimiters.
    for pattern in (
        r"(?<![^\W_])\*\*(?=\S)(.+?)(?<=\S)\*\*(?![^\W_])",
        r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)",
    ):
        for match in re.finditer(pattern, source):
            start, end = match.span(1)
            keep[match.start() : start] = [False] * (start - match.start())
            keep[end : match.end()] = [False] * (match.end() - end)
    # Parallel's PDF excerpts sometimes contain an inline heading marker after
    # line flattening. A standalone 2-6 hash token is the only such exception;
    # retain single # (numbers/tags), attached hashes and all other punctuation.
    for match in re.finditer(r"(?<!\S)#{2,6}(?!\S)", source):
        keep[match.start() : match.end()] = [False] * len(match.group())
    chars: list[tuple[str, int, int]] = []
    for i, char in enumerate(source):
        if not keep[i]:
            continue
        if char.isspace():
            if chars and chars[-1][0] == " ":
                chars[-1] = (" ", chars[-1][1], i + 1)
            else:
                chars.append((" ", i, i + 1))
        else:
            chars.append((char, i, i + 1))
    return chars


def anchor_quote(quote: str, excerpt: str) -> str | None:
    """Return the exact receipt, or one unambiguous raw slice for a display quote.

    For a clause-sized quote, PDF spacing may be missing or inserted inside words.
    Match only the identical non-whitespace character sequence at source boundaries,
    then return its RAW substring, never the model's proposed word segmentation.
    Full raw source context still goes to independent entailment review, including
    all negations. Provenance matching is not semantic approval.
    """
    if not quote.strip():
        return None
    if quote in excerpt:
        return quote
    wanted = " ".join(quote.split())
    chars = _display_chars(excerpt)
    display = "".join(char for char, _, _ in chars)
    start = display.find(wanted)
    if start < 0:
        if len(wanted.split()) < _MIN_SPACING_WORDS:
            return None
        positions = [i for i, (char, _, _) in enumerate(chars) if not char.isspace()]
        compact = "".join(chars[i][0] for i in positions)
        needle = "".join(wanted.split())
        offset = compact.find(needle)
        if offset < 0 or compact.find(needle, offset + 1) >= 0:
            return None
        start, end = positions[offset], positions[offset + len(needle) - 1] + 1
    else:
        if display.find(wanted, start + 1) >= 0:
            return None
        end = start + len(wanted)
    # A formatting repair must not turn a partial word into a new receipt.
    if (start and display[start - 1].isalnum() and wanted[0].isalnum()) or (
        end < len(display) and display[end].isalnum() and wanted[-1].isalnum()
    ):
        return None
    return excerpt[chars[start][1] : chars[end - 1][2]]

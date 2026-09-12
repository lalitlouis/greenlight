"""Conservative display-text matching that returns an unchanged source substring.

This is not fuzzy matching or a Markdown renderer. Unsupported/truncated markup
stays literal. Words, punctuation, case and order are never repaired.
"""

from __future__ import annotations

import re


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

    Only source formatting is interpreted; the requested quote is plain text with
    whitespace collapsed. Never borrow text from another citation. Full raw source
    context still goes to independent entailment review, including all negations.
    """
    if not quote.strip():
        return None
    if quote in excerpt:
        return quote
    wanted = " ".join(quote.split())
    chars = _display_chars(excerpt)
    display = "".join(char for char, _, _ in chars)
    start = display.find(wanted)
    if start < 0 or display.find(wanted, start + 1) >= 0:
        return None
    end = start + len(wanted)
    # A formatting repair must not turn a partial word into a new receipt.
    if (start and display[start - 1].isalnum() and wanted[0].isalnum()) or (
        end < len(display) and display[end].isalnum() and wanted[-1].isalnum()
    ):
        return None
    return excerpt[chars[start][1] : chars[end - 1][2]]

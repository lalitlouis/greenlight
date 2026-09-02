"""Rightsholder-shaped names in finding prose — the statute-section rule applied to
names (review 2026-09-01, A9).

An ownership claim ("100% controlled by Sony Music Publishing") is the product's demo
moment; a licensor named from memory is the fabrication class wearing a suit. ONE
extractor lives here and is imported by the filing gate (toolbelt) and by both eval
gates, so the gate and the assertion cannot drift apart."""

from __future__ import annotations

import re

# up to three capitalised words then a corporate/institutional suffix
RIGHTSHOLDER_RE = re.compile(
    r"\b((?:[A-Z][\w&'.\-/]*\s+){0,3}"
    r"(?:Music|Publishing|Records|Recordings|Entertainment|Pictures|Studios|Society|Museum"
    r"|Estate|Inc\.?|LLC|Group|Corporation|Company|Foundation|Trust|Archive|Archives))\b"
)
SUFFIX_TOKENS = {
    "music", "publishing", "records", "recordings", "entertainment", "pictures", "studios",
    "society", "museum", "estate", "inc", "llc", "group", "corporation", "company",
    "foundation", "trust", "archive", "archives", "the", "of", "and", "for", "a", "an",
}  # fmt: skip
# "Ringgold v. Black Entertainment Television" names a CASE, not a licensor — the
# first gate run flagged it as an untraceable rightsholder (false positive).
_CASE_CITE_BEFORE = re.compile(r"\bv(?:s)?\.?\s*$", re.IGNORECASE)
# ...and the plaintiff side: "Warner Bros. Entertainment Inc. v. S. Reed Christenson"
_CASE_CITE_AFTER = re.compile(
    r"^\.?(?:\s+(?:Inc|LLC|Ltd|Corp|Co)\.?,?)?\s+v(?:s)?\.?\s", re.IGNORECASE
)
# sentence-initial or verb-initial capitalised words glued onto a name ("Under Warner
# Bros. Entertainment", "Licensed by …") are not part of the holder's name
_LEAD_STOPWORDS = {
    "under", "licensed", "license", "licence", "in", "from", "by", "the", "a", "an", "per",
    "see", "apply", "contact", "via", "with", "and", "or", "of", "to", "at", "on", "for",
    "as", "its", "this", "that", "these", "obtain", "secure", "through", "while", "both",
    "if", "when", "where", "because", "since", "although", "unless", "then", "also",
}  # fmt: skip


def norm(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).split())


def distinctive_tokens(name: str) -> list[str]:
    """The tokens that identify the holder — never the suffix or a stopword."""
    return [t for t in norm(name).split() if t not in SUFFIX_TOKENS]


def rightsholder_names(text: str) -> list[str]:
    """Licensor-shaped proper nouns in prose, case citations excluded."""
    out: list[str] = []
    for m in RIGHTSHOLDER_RE.finditer(text or ""):
        start = m.start(1)
        if _CASE_CITE_BEFORE.search(text[max(0, start - 8) : start]):
            continue
        if _CASE_CITE_AFTER.match(text[m.end(1) : m.end(1) + 24]):
            continue
        words = m.group(1).strip().split()
        while len(words) > 1 and words[0].lower().strip(".,") in _LEAD_STOPWORDS:
            words.pop(0)
        name = " ".join(words)
        if not distinctive_tokens(name):
            continue
        out.append(name)
    return out


def untraceable_rightsholders(text: str, excerpts: str) -> list[str]:
    """Names in `text` whose distinctive tokens do not ALL appear in `excerpts`."""
    have = set(norm(excerpts).split())
    return sorted(
        {n for n in rightsholder_names(text) if not all(t in have for t in distinctive_tokens(n))}
    )

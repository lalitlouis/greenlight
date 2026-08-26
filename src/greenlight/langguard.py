"""Language guard: detect probably-non-English screenplays at upload.

The analysis is calibrated for English-language scripts under US clearance
doctrine. A non-English script would silently receive Anglo-calibrated output
wearing full confidence — this guard converts that silent failure into a
visible, honest warning. Heuristic and deterministic: no model, no network.
"""

from __future__ import annotations

import re

# The most frequent English words; a screenplay that barely uses them is very
# unlikely to be English. Deliberately short — this is a smoke test, not NLP.
_COMMON_EN_WORDS = (
    "the a an and or of to in on at is are was were be been i you he she it we "
    "they this that with for as his her not but from have has had what who"
)
_COMMON_EN = frozenset(_COMMON_EN_WORDS.split())
_WORD = re.compile(r"[a-zA-Z']+")
_MIN_WORDS = 80  # below this, too short to judge — let it pass
_EN_THRESHOLD = 0.12  # English prose runs ~0.3+; other Latin languages ~0.0-0.05


def english_confidence(text: str) -> float | None:
    """Fraction of words that are common-English. None = too short to judge."""
    sample = text[:60_000]
    # non-Latin scripts: if a large share of characters are outside Latin-1,
    # the common-word test is meaningless and the answer is already "not English"
    latin_ceiling = 0x24F  # Latin Extended-B ends here; beyond = CJK/Arabic/etc.
    non_latin_threshold = 0.3
    letters = [c for c in sample if c.isalpha()]
    if letters:
        non_latin = sum(1 for c in letters if ord(c) > latin_ceiling)
        if non_latin / len(letters) > non_latin_threshold:
            return 0.0
    words = [w.lower() for w in _WORD.findall(sample)]
    if len(words) < _MIN_WORDS:
        return None
    return sum(1 for w in words if w in _COMMON_EN) / len(words)


def probably_english(text: str) -> bool:
    conf = english_confidence(text)
    return conf is None or conf >= _EN_THRESHOLD

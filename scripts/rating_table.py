#!/usr/bin/env python3
"""B1: parse official CARA rationales into (intensity, category) pairs and
build the frequency table P(rating | descriptor set).

Parse failures are a first-class output, never a silent drop — they are
either vocabulary gaps or genuine oddities, and both are interesting.
Raw strings stay untouched in the harvest file; this script only reads.

  .venv/bin/python scripts/rating_table.py [min_year]
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / ".cache" / "ratings_ingest" / "rationales.jsonl"
OUT = ROOT / ".cache" / "ratings_ingest" / "descriptor_table.json"

INTENSITIES = [
    "pervasive",
    "graphic",
    "strong bloody",
    "strong",
    "intense",
    "sustained",
    "crude",
    "brief",
    "mild",
    "some",
    "partial",
    "brutal",
    "grisly",
    "explicit",
]
CATEGORIES = {
    "language": ["language", "profanity", "cursing"],
    "violence": [
        "violence",
        "violent content",
        "violent images",
        "violent material",
        "combat",
        "gunplay",
        "shootings",
        "torture",
        "destruction",
        "violent",
    ],
    "sexual_content": [
        "sexual content",
        "sexuality",
        "sexual material",
        "sex references",
        "sexual references",
        "sensuality",
        "sexual situations",
        "sexual humor",
        "sexual dialogue",
        "erotic sexuality",
        "sex",
    ],
    "nudity": ["nudity"],
    "drugs": [
        "drug use",
        "drug content",
        "drug material",
        "drug references",
        "drug reference",
        "drugs",
        "drug",
        "substance abuse",
        "substance use",
    ],
    "alcohol": ["alcohol use", "alcohol abuse", "drinking", "alcohol", "teen partying"],
    "smoking": ["smoking", "tobacco"],
    "thematic": [
        "thematic material",
        "thematic elements",
        "thematic content",
        "mature thematic content",
        "mature themes",
        "themes",
    ],
    "gore": ["gore", "grisly images", "bloody images"],
    "disturbing": [
        "disturbing images",
        "disturbing content",
        "disturbing violent",
        "disturbing material",
        "disturbing behavior",
        "disturbing",
        "injury images",
    ],
    "peril": ["peril", "menace", "terror", "frightening", "scary images", "scary"],
    "action": ["action"],
    "crude_humor": [
        "crude humor",
        "rude humor",
        "crude and sexual humor",
        "crude content",
        "crude material",
        "rude material",
        "crude",
    ],
    "horror": ["horror"],
    "suggestive": [
        "suggestive material",
        "suggestive content",
        "innuendo",
        "suggestive references",
        "suggestive humor",
        "suggestive",
    ],
    "suicide": ["suicide", "self-harm", "self harm"],
}
_PREFIX = re.compile(r"^Rated\s+(G|PG-13|PG|R|NC-17)\s+for\s+", re.I)
_SPLIT = re.compile(r",\s*(?:and\s+)?|\s+and\s+")


def parse_rationale(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """-> ([(intensity, category)...], [unparsed segments])."""
    m = _PREFIX.match(text.strip())
    body = text.strip()[m.end() :] if m else text.strip()
    body = body.rstrip(".").strip('"“” ')
    pairs: list[tuple[str, str]] = []
    fails: list[str] = []
    segments = [x.strip().lower() for x in _SPLIT.split(body) if x.strip()]
    merged: list[str] = []
    for seg in segments:
        # "strong, bloody violence" splits as "strong" + "bloody violence" —
        # a bare-intensity fragment re-binds to what follows it
        if merged and merged[-1] in INTENSITIES:
            merged[-1] = f"{merged[-1]} {seg}"
        else:
            merged.append(seg)
    for seg in merged:
        if not seg:
            continue
        intensity = ""
        for i in INTENSITIES:
            if re.search(rf"\b{re.escape(i)}\b", seg):
                intensity = i
                break
        cat = ""
        best = 0
        for c, variants in CATEGORIES.items():
            for v in variants:
                if v in seg and len(v) > best:
                    cat, best = c, len(v)
        if cat:
            pairs.append((intensity or "unmodified", cat))
        else:
            fails.append(seg)
    return pairs, fails


def main() -> int:
    min_year = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    rows = [json.loads(line) for line in SRC.read_text().splitlines() if line.strip()]
    with_r = [r for r in rows if r.get("rationale")]
    by_decade = Counter((r["year"] // 10) * 10 for r in with_r)
    print(f"inventory: {len(with_r)}/{len(rows)} rows carry a rationale")
    for dec in sorted(by_decade):
        print(f"  {dec}s: {by_decade[dec]}")

    scoped = [r for r in with_r if r["year"] >= min_year]
    table: dict[str, Counter] = defaultdict(Counter)  # descriptor -> rating counts
    combo: dict[str, Counter] = defaultdict(Counter)  # frozenset-of-cats key -> ratings
    all_fails: list[dict] = []
    films: list[dict] = []
    parsed_films = 0
    for r in scoped:
        pairs, fails = parse_rationale(r["rationale"])
        if fails:
            all_fails.append({"title": r["title"], "segments": fails, "raw": r["rationale"]})
        if not pairs:
            continue
        films.append(
            {
                "title": r["title"],
                "year": r["year"],
                "year_rated": r.get("year_rated", ""),
                "rating": r["rating"],
                "pairs": pairs,
            }
        )
        parsed_films += 1
        rating = r["rating"]
        for intensity, cat in pairs:
            table[f"{intensity} {cat}"][rating] += 1
            table[cat][rating] += 1
        combo["+".join(sorted({c for _, c in pairs}))][rating] += 1

    print(
        f"\nparsed {parsed_films}/{len(scoped)} scoped films "
        f"({len(all_fails)} with unparsed segments)"
    )
    print("\ntop descriptors — P(rating | descriptor), n:")
    interesting = sorted(table.items(), key=lambda kv: -sum(kv[1].values()))[:18]
    for desc, counts in interesting:
        n = sum(counts.values())
        dist = " ".join(f"{k}:{100 * v // n}%" for k, v in counts.most_common(3))
        print(f"  {desc:32} n={n:<5} {dist}")

    sep = []
    for desc, counts in table.items():
        n = sum(counts.values())
        if n >= 30:
            top_rating, top_n = counts.most_common(1)[0]
            sep.append((top_n / n, n, desc, top_rating))
    sep.sort(reverse=True)
    print("\nsharpest separators (n>=30):")
    for frac, n, desc, rating in sep[:12]:
        print(f"  {desc:32} -> {rating} {100 * frac:.0f}% (n={n})")

    OUT.write_text(
        json.dumps(
            {
                "min_year": min_year,
                "films_parsed": parsed_films,
                "descriptors": {k: dict(v) for k, v in table.items()},
                "combos": {k: dict(v) for k, v in combo.items()},
                "films": films,
                "parse_failures": all_fails,
            },
            indent=1,
        )
    )
    print(f"\nsaved: {OUT} | parse-failure list: {len(all_fails)} films")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

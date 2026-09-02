#!/usr/bin/env python3
"""Comparables benchmark for the RATIONALE-SPACE corpus (run 17).

`query_precedent` now searches `cara_rationales` — 4,733 official
filmratings.com rationale strings embedded on their "for ..." clause — with a
CARA-style descriptor profile, not a genre capsule. This benchmark asks the
question that corpus can answer: does a descriptor profile land among films
CARA rated for the same content, does the shared inverse-distance vote track
the rating those descriptors pattern to, and is every neighbour's excerpt its
own official rationale (the eval assertion, exercised live)?

The pre-run-17 version of this script probed genre affinity on the plot-space
table; that path is retired, and genre affinity is a documented casualty of
run 17 (docs/plans/run17-rationale-space.md, P4) — not a regression.

Live embeddings + ClickHouse (a few cents). Not a unit test: `make comps-gate`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from greenlight.tools.toolbelt import (  # noqa: E402
    _clickhouse_client,
    _embed,
    boundary_eval,
    comps_weighted_majority,
)

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
R_ = "\033[0m"


def neighbours(profile: str, k: int = 8) -> list[dict]:
    """Mirror of query_precedent's query: same table, same columns, same order."""
    vec = _embed(profile)
    rows = (
        _clickhouse_client()
        .query(
            """
            SELECT title, year, rating, rationale,
                   cosineDistance(embedding, %(vec)s) AS distance
            FROM cara_rationales
            ORDER BY distance ASC, year DESC
            LIMIT %(k)s
            """,
            parameters={"vec": vec, "k": k},
        )
        .result_rows
    )
    return [
        {"title": t, "year": y, "rating": r, "rationale": ra, "distance": float(d)}
        for t, y, r, ra, d in rows
    ]


# Descriptor profiles (what the desk now sends), the rating band the measured
# boundary expects, and the descriptor phrases boundary_eval should agree on.
PROBES = [
    {
        "name": "pervasive language + strong violence (hard R)",
        "profile": "for pervasive language, strong bloody violence and some drug use",
        "descriptors": ["pervasive language", "strong bloody violence", "some drug use"],
        "majority_in": ["R"],
    },
    {
        "name": "fixture-shaped: language, brief drugs, some violence",
        "profile": "for language, brief drug use and some violence",
        "descriptors": ["language", "brief drug use", "some violence"],
        "majority_in": ["R", "PG-13"],
    },
    {
        "name": "one-F-word PG-13 (brief strong language)",
        "profile": "for brief strong language",
        "descriptors": ["brief strong language"],
        "majority_in": ["PG-13"],
    },
    {
        "name": "mild thematic elements (PG)",
        "profile": "for mild thematic elements and some language",
        "descriptors": ["mild thematic elements", "some language"],
        "majority_in": ["PG", "PG-13"],
    },
    {
        "name": "graphic nudity + sexual content (R/NC-17)",
        "profile": "for graphic nudity, strong sexual content and language",
        "descriptors": ["graphic nudity", "strong sexual content", "language"],
        "majority_in": ["R", "NC-17"],
    },
]

# The retired genre capsule, printed once so the mismatch it produces on the
# rationale table stays visible: a plot sentence lands nowhere useful here.
OLD_STYLE_GENRE_CAPSULE = (
    "A dialogue-driven biographical drama about the founding of a technology "
    "company, told through legal depositions and campus scenes."
)


def main() -> int:
    passes = 0
    checks = 0

    print(f"{DIM}retired genre capsule against the rationale table (expect noise):{R_}")
    for n in neighbours(OLD_STYLE_GENRE_CAPSULE, 5):
        print(f"  {DIM}{n['distance']:.3f}  {n['rating']:<6} {n['title']}{R_}")

    for probe in PROBES:
        ns = neighbours(probe["profile"], 8)
        majority = comps_weighted_majority(ns)
        boundary = boundary_eval(probe["descriptors"])
        pred_set = boundary.get("prediction_set") or []

        print(f"\n{probe['name']}  (weighted majority: {majority}; boundary set: {pred_set})")
        for n in ns:
            print(
                f"  {n['distance']:.3f}  {n['rating']:<6} {n['title']}  "
                f"{DIM}{n['rationale'][:70]}{R_}"
            )

        def grade(ok: bool, label: str) -> None:
            nonlocal passes, checks
            checks += 1
            passes += ok
            print(f"  [{GREEN}PASS{R_}]" if ok else f"  [{RED}MISS{R_}]", label)

        grade(majority in probe["majority_in"], f"weighted majority in {probe['majority_in']}")
        grade(
            all(
                re.match(rf"^Rated\s+{re.escape(n['rating'])}\s+for\s+", n["rationale"], re.I)
                for n in ns
            ),
            "every neighbour's excerpt is its own official rationale",
        )
        grade(
            not boundary.get("unmatched"),
            f"boundary parses every descriptor (unmatched: {boundary.get('unmatched')})",
        )
        grade(
            not pred_set or majority in pred_set or len(pred_set) > 1,
            "instruments agree: the vote sits inside the conformal set (or the set is not "
            "a singleton)",
        )

    print(f"\n{passes}/{checks}")
    return 0 if passes == checks else 1


if __name__ == "__main__":
    raise SystemExit(main())

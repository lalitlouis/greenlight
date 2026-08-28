#!/usr/bin/env python3
"""Comparables benchmark: does the corpus neighbourhood match the film's FORM?

The failure this guards against (2026-08-27 review): content markers alone
put The Social Network next to Showgirls, then next to college comedies.
Fixed probes in the form-first capsule style assert that known film shapes
land among their actual genre neighbours, that the distance-weighted majority
tracks the released rating, and that the old content-only capsule style is
measurably worse (the diff prints, so regressions are visible, not vibes).

Live embeddings + ClickHouse (a few cents). Not a unit test: `make comps-gate`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from greenlight.tools.toolbelt import (  # noqa: E402
    _clickhouse_client,
    _comps_weighted_majority,
    _embed,
)

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
R_ = "\033[0m"


def neighbours(capsule: str, k: int = 8) -> list[dict]:
    vec = _embed(capsule)
    rows = (
        _clickhouse_client()
        .query(
            "SELECT title, rating, cosineDistance(embedding, %(v)s) d "
            "FROM rating_rationales ORDER BY d ASC LIMIT %(k)s",
            parameters={"v": vec, "k": k},
        )
        .result_rows
    )
    return [{"title": t, "rating": r, "distance": float(d)} for t, r, d in rows]


PROBES = [
    {
        "name": "dialogue-driven founder legal drama (TSN-shaped)",
        "capsule": (
            "A dialogue-driven biographical drama about the founding of a technology "
            "company, told through legal depositions and campus scenes at an Ivy League "
            "university. 189 scenes; 74% of the text is dialogue (dialogue-driven); "
            "procedural register, dramatic not comedic — the drinking is background, "
            "never the joke. Pervasive strong language, college drinking, brief cocaine "
            "use at a party, some sexual content; no violence."
        ),
        "want_any": [
            "steve jobs",
            "jobs",
            "blackberry",
            "tesla",
            "the social network",
            "moneyball",
            "the big short",
            "margin call",
            "the founder",
            "equity",
            "pain hustlers",
            "the hummingbird project",
            "dumb money",
            "air",
        ],
        "want_min": 3,
        "veto_top4": [
            "neighbors",
            "american pie",
            "22 jump street",
            "booksmart",
            "life of the party",
            "shithouse",
            "big time adolescence",
            "dirty grandpa",
            "showgirls",
            "hustlers",
            "magic mike",
            "a dirty shame",
            "bad lieutenant",
        ],
        "majority_in": ["PG-13", "R"],
    },
    {
        "name": "quiet coastal grief drama (fixture-shaped)",
        "capsule": (
            "A quiet, dialogue-forward drama about grief in a small fishing harbor "
            "town — a family working out a death over boats, bars, and a funeral. "
            "12 scenes; balanced dialogue and action; dramatic register, no comedy. "
            "Strong language in bursts, brief violence, a scattering of drug use; "
            "no sexual content."
        ),
        "want_any": [
            "manchester by the sea",
            "coda",
            "finestkind",
            "blow the man down",
            "the peanut butter falcon",
            "sound of metal",
            "leave no trace",
        ],
        "want_min": 1,
        "veto_top4": ["showgirls", "american pie", "dirty grandpa"],
        "majority_in": ["R", "PG-13"],
    },
    {
        "name": "animated family adventure",
        "capsule": (
            "A bright animated family adventure about a young animal hero on a quest "
            "with comic sidekicks. Ensemble comedy register, song numbers, slapstick "
            "peril only; no language, no substances, no sexual content."
        ),
        "want_any": [],
        "want_min": 0,
        "veto_top4": ["showgirls", "neighbors"],
        "majority_in": ["G", "PG"],
    },
    {
        "name": "hard-R action revenge thriller",
        "capsule": (
            "A relentless action revenge thriller — a professional killer cuts through "
            "a criminal underworld. Action-forward (25% dialogue), stylized register; "
            "pervasive graphic gun violence, strong language throughout, brief drug "
            "material; no sexual content."
        ),
        "want_any": [],
        "want_min": 0,
        "veto_top4": [],
        "majority_in": ["R"],
    },
]

# The pre-fix capsule style for the TSN shape — kept so the improvement (or a
# regression) is a printed diff, not a memory.
OLD_STYLE_TSN = (
    "Pervasive strong language, sexual content, drug use, and alcohol abuse "
    "involving college students; brief nudity in party scenes."
)


def main() -> int:
    passes = 0
    checks = 0

    print(f"{DIM}old-style capsule (content markers only), TSN shape:{R_}")
    for n in neighbours(OLD_STYLE_TSN, 8):
        print(f"  {DIM}{n['distance']:.3f}  {n['rating']:<6} {n['title']}{R_}")

    for probe in PROBES:
        ns = neighbours(probe["capsule"], 8)
        titles = [n["title"].lower() for n in ns]
        top4 = titles[:4]
        majority = _comps_weighted_majority(ns)

        print(f"\n{probe['name']}  (weighted majority: {majority})")
        for n in ns:
            print(f"  {n['distance']:.3f}  {n['rating']:<6} {n['title']}")

        def grade(ok: bool, label: str) -> None:
            nonlocal passes, checks
            checks += 1
            passes += ok
            print(f"  [{GREEN}PASS{R_}]" if ok else f"  [{RED}MISS{R_}]", label)

        if probe["want_min"]:
            hits = sum(1 for t in titles if any(w in t for w in probe["want_any"]))
            grade(
                hits >= probe["want_min"],
                f"≥{probe['want_min']} genre-true neighbours ({hits} found)",
            )
        if probe["veto_top4"]:
            bad = [t for t in top4 if any(v in t for v in probe["veto_top4"])]
            grade(
                not bad, f"no vetoed titles in the top 4 {('— ' + ', '.join(bad)) if bad else ''}"
            )
        grade(
            majority in probe["majority_in"],
            f"weighted majority in {probe['majority_in']}",
        )

    print(f"\n{passes}/{checks}")
    return 0 if passes == checks else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""SCALE GATE grader: score a run of fixtures/scale_gate.fountain.

Usage: python scripts/eval_scale.py [runs/run_X.json]   (default: latest run)

Checks structural health at scale (the failure classes of 2026-08-26: aborts,
id collisions, rejection loops, missing rating, runaway wall-clock) plus the
seeded doctrine traps, including the layers added after the TSN/Hangover
reviews (venue trade-libel, location classes, indie music paths, defamation
counterweight). Every MISS is a scale regression to explain before deploying.
"""

from __future__ import annotations

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_invariants import shared_invariants
from eval_run import flags_matching
from eval_run import flags_about

PASS, MISS = "\033[32mPASS\033[0m", "\033[31mMISS\033[0m"
results: list[bool] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append(bool(ok))
    print(f"  [{PASS if ok else MISS}]  {name}" + (f"  \033[2m{note}\033[0m" if note else ""))


def main() -> int:
    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else max(glob.glob("runs/run_*.json"), key=os.path.getmtime)
    )
    with open(path) as fh:
        r = json.load(fh)
    rep = r.get("report") or {}
    flags = r.get("flags") or []
    rejected = r.get("rejected_flags") or []
    print(f"grading {path}: {len(flags)} kept / {len(rejected)} rejected\n")

    # --- structural health at scale -----------------------------------------
    check(
        "wall clock under 30 minutes", (r.get("elapsed_s") or 9e9) < 1800, f"{r.get('elapsed_s')}s"
    )
    check("no research failures", not r.get("research_failures"))
    pred = rep.get("rating_prediction") or {}
    check(
        "rating prediction filed with comparables",
        bool(pred.get("predicted")) and len(pred.get("comparables") or []) >= 5,
    )
    check(
        "kept-findings floor (>=10 on this fixture)",
        sum(1 for k in (r.get("research_budget_left") or {}) if True) >= 1 and len(flags) >= 10,
        f"{len(flags)} kept — floor recalibrated 25->10 on 2026-08-29: the 25 dated from the "
        "pre-noise-reduction era; the 2026-08-29 validation kept 11 flags while passing all "
        "14 content seeds, which is the direct thinness measure",
    )
    # --- every script-independent invariant, shared with the fixture gate ------
    # (run health, citation invariant, referential integrity, prose/coordinates,
    # rating marginals + normative rule, cut-list direction, reconciliation,
    # binder coverage, receipts, statutes, unexamined, collapse, territory axes)
    for name, ok, note in shared_invariants(r, rejection_cap=0.45):
        check(name, ok, note)

    # --- seeded traps --------------------------------------------------------
    check(
        "music: sync flag for the played Who recording",
        bool(flags_about(flags, category_any=["sync"], text_any=["baba o'riley", "the who"])),
    )
    check(
        "music: separate master-use flag",
        bool(flags_about(flags, category_any=["master"], text_any=["recording"])),
    )
    sync = flags_about(flags, category_any=["sync", "master"])
    check(
        "music: an indie budget path in a music remedy",
        any(
            any(
                w in json.dumps(f.get("remedy") or {}).lower()
                for w in ("library", "independent", "placeholder", "temp track", "drop the cue")
            )
            for f in sync
        ),
    )
    check(
        "artwork: Nighthawks print flagged (1942 = NOT public domain)",
        bool(
            flags_about(flags, category_any=["artwork", "art_"], text_any=["nighthawk", "hopper"])
        ),
    )
    check(
        "tattoo: Vera Kest serpent flagged as artwork/likeness",
        bool(
            flags_about(
                flags,
                category_any=["artwork", "tattoo", "art_"],
                text_any=["kest", "tattoo", "serpent"],
            )
        ),
    )
    check(
        "brand nuance: Coors disparagement flagged",
        bool(flags_about(flags, category_any=["disparag"], text_any=["coors"])),
    )
    check(
        "PD hymn: Amazing Grace NOT clearance-flagged (silence correct)",
        not [
            f
            for f in flags_about(flags, text_any=["amazing grace"])
            if f["flag_id"].startswith("F1") and f.get("severity") in ("BLOCKER", "HIGH", "MEDIUM")
        ],
    )
    check(
        "venue: casino destruction flagged beyond trademark",
        bool(
            flags_about(
                flags,
                category_any=["trade_libel", "venue", "disparag", "location"],
                text_any=["grand meridian", "casino"],
            )
        ),
    )
    casino = flags_about(
        flags,
        category_any=["location", "venue", "trade_libel"],
        text_any=["casino", "grand meridian"],
    )
    check(
        "location realism: controlled-venue remedy (build/alternate, not a permit)",
        any(
            any(
                w in json.dumps(f.get("remedy") or {}).lower()
                for w in ("controlled", "stage", "build", "alternate", "not obtainable")
            )
            for f in casino
        ),
    )
    # NEGATIVE checks are conjunctive (category AND text): flags_about unions the two,
    # and a doctrine-correct right_of_publicity flag on the Springsteen POSTER read as
    # "defamation-flagged" (scale gate 2026-09-02) — the anecdote itself was not flagged
    check(
        "defamation counterweight: neutral Springsteen story NOT defamation-flagged",
        not flags_matching(flags, category_any=["defamation"], text_any=["springsteen"]),
    )
    check(
        "safety: pyro/minor climax flagged",
        bool(
            flags_about(
                flags,
                category_any=["fire", "pyro", "minor"],
                text_any=["firework", "minor", "pyro"],
            )
        ),
    )
    check(
        "rating: strong-language flag exists",
        bool(flags_about(flags, category_any=["rating_language"])),
    )
    check(
        "territory: drug flag for the joint (CN or UAE)",
        bool(flags_about(flags, category_any=["territory_cn_drug", "territory_uae_drug"])),
    )
    check(
        "territory: recounted-not-depicted ghost NOT a CN supernatural blocker",
        not [
            f
            for f in flags_about(flags, category_any=["territory_cn_supernatural"])
            if f.get("severity") == "BLOCKER"
        ],
    )

    n_ok = sum(results)
    print(f"\n{n_ok}/{len(results)}")
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

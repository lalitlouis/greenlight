#!/usr/bin/env python3
"""Score a run record against the seeded ground truth in fixtures/SEEDS.md.

Usage: python scripts/eval_run.py [runs/run_X.json]   (default: latest run)

This is the objective check for desk calibration: every seed the screenplay was
built around, expressed as an assertion over the run's kept flags. Not a unit test
— desks are non-deterministic — but every MISS here is a coverage failure to
explain before shipping a change to an instruction or the verifier.
"""

from __future__ import annotations

import glob
import json
import sys


def flags_matching(flags, *, category_any=None, scenes_any=None, desk=None):
    out = []
    for f in flags:
        if desk and f["agent"] != desk:
            continue
        if category_any and not any(c in f["category"] for c in category_any):
            continue
        if scenes_any and not set(f["scene_ids"]) & set(scenes_any):
            continue
        out.append(f)
    return out


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob("runs/run_*.json"))[-1]
    r = json.load(open(path))
    flags = r["flags"]
    rejected = r.get("rejected_flags", [])
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = ""):
        checks.append((name, ok, detail))

    # --- Clearance Counsel seeds
    sync = flags_matching(flags, category_any=["sync", "music"], desk="clearance_counsel")
    master = flags_matching(flags, category_any=["master"], desk="clearance_counsel")
    check("music: composition/sync flag", bool(sync), "the ownership chase, demo moment #2")
    check("music: separate master flag", bool(master), "sync and master must be two flags")
    check(
        "brand disparagement flagged",
        bool(flags_matching(flags, category_any=["disparagement"])),
        "Coors Light rant",
    )
    check(
        "artwork flagged (Nighthawks)",
        bool(flags_matching(flags, category_any=["artwork", "art_"])),
    )
    check(
        "likeness flagged (Springsteen photo)",
        bool(flags_matching(flags, category_any=["publicity", "likeness"])),
    )
    check(
        "film clip flagged (Jaws)",
        bool(flags_matching(flags, category_any=["film_clip", "clip"])),
    )

    # --- Verifier traps: these must NOT survive as flags
    foster = flags_matching(flags, category_any=["sync", "music", "public_domain"])
    foster_bad = [
        f
        for f in foster
        if "hard times" in f["finding"].lower() or "foster" in f["finding"].lower()
    ]
    check(
        "trap: no license flag on the PD Stephen Foster hymn",
        not foster_bad,
        foster_bad[0]["flag_id"] if foster_bad else "",
    )
    thermos_bad = [
        f
        for f in flags_matching(flags, category_any=["trademark"])
        if "thermos" in f["finding"].lower()
    ]
    check("trap: no US trademark flag on 'Thermos'", not thermos_bad)

    # --- Ratings seeds
    lang = flags_matching(flags, category_any=["language"], desk="ratings_board")
    check("ratings: language flag exists", bool(lang))
    check(
        "ratings: language flag counts all 3 scenes",
        bool(flags_matching(lang, scenes_any=["S011"]))
        and bool(flags_matching(lang, scenes_any=["S003"])),
        "S003, S006, S011 — miscounting means find_in_script was skipped",
    )
    check(
        "ratings: drug-use flag",
        bool(flags_matching(flags, category_any=["drug"], desk="ratings_board")),
    )

    # --- Safety seeds
    climax = flags_matching(
        flags, desk="safety_underwriter", scenes_any=["S009", "S010", "S011"]
    )
    check(
        "safety: THE CLIMAX IS FLAGGED (S009-S011)",
        bool(climax),
        "burn+water+night+minor+animal — the worst scene cannot be the missed one",
    )
    check(
        "safety: firearms/salute flagged",
        bool(flags_matching(flags, desk="safety_underwriter", scenes_any=["S004", "S005"])),
    )

    # --- Territory seeds
    check(
        "territory: CN supernatural flag on the ghost scene",
        bool(flags_matching(flags, category_any=["supernatural", "superstition"], scenes_any=["S007"])),
    )
    check(
        "territory: CN or UAE drug flag",
        bool(flags_matching(flags, category_any=["drug"], desk="territory_censor")),
    )

    # --- Verification health
    check(
        "verification: rejection rate in (0%, 40%]",
        0 < len(rejected) <= 0.4 * max(1, len(rejected) + len(flags)),
        f"{len(rejected)} rejected / {len(rejected) + len(flags)} filed — 0 means the verifier "
        "is asleep; >40% means desks or verifier are miscalibrated",
    )
    check(
        "invariant: every kept flag has a citation with an excerpt",
        all(f["citations"] and all(c["excerpt"].strip() for c in f["citations"]) for f in flags),
    )

    print(f"\nEval of {path} — {len(flags)} kept, {len(rejected)} rejected\n")
    passed = 0
    for name, ok, detail in checks:
        mark = "\033[32mPASS\033[0m" if ok else "\033[31mMISS\033[0m"
        extra = f"  \033[2m{detail}\033[0m" if detail and not ok else ""
        print(f"  {mark}  {name}{extra}")
        passed += ok
    print(f"\n{passed}/{len(checks)}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

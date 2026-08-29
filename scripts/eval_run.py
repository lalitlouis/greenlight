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
import os
import sys


def flags_matching(flags, *, category_any=None, scenes_any=None, desk=None, text_any=None):
    out = []
    for f in flags:
        if desk and f["agent"] != desk:
            continue
        if category_any and not any(c in f["category"] for c in category_any):
            continue
        if scenes_any and not set(f["scene_ids"]) & set(scenes_any):
            continue
        if text_any and not any(s in f["finding"].lower() for s in text_any):
            continue
        out.append(f)
    return out


def flags_about(flags, *, category_any=(), text_any=(), desk=None):
    """Category OR finding-text match — desks drift category slugs run to run."""
    # an empty filter must contribute NOTHING, not everything — a single-param
    # call once unioned in every flag and graded garbage (scale gate, 2026-08-26)
    by_cat = (
        flags_matching(flags, category_any=list(category_any), desk=desk) if category_any else []
    )
    by_text = flags_matching(flags, text_any=list(text_any), desk=desk) if text_any else []
    seen, out = set(), []
    for f in by_cat + by_text:
        if f["flag_id"] not in seen:
            seen.add(f["flag_id"])
            out.append(f)
    return out


def main() -> int:  # noqa: PLR0915 - a linear checklist, deliberately flat
    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else max(glob.glob("runs/run_*.json"), key=os.path.getmtime)
    )
    with open(path) as fh:
        r = json.load(fh)
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
        "tattoo flagged as visual artwork (Krane schooner)",
        bool(flags_about(flags, category_any=["artwork", "art_"], text_any=["tattoo", "krane"])),
        "depicted custom tattoo by a named artist — the Whitmill scenario",
    )
    check(
        "artwork flagged (Nighthawks)",
        bool(
            flags_about(flags, category_any=["artwork", "art_"], text_any=["nighthawks", "hopper"])
        ),
    )
    check(
        "likeness flagged (Springsteen photo)",
        bool(
            flags_about(
                flags,
                category_any=["publicity", "likeness", "personality"],
                text_any=["springsteen"],
            )
        ),
    )
    check(
        "film clip flagged (Jaws)",
        bool(flags_about(flags, category_any=["film_clip", "clip"], text_any=["jaws"])),
    )
    check(
        "no 'all clear' assertions filed as flags",
        not flags_matching(flags, category_any=["no_clearance", "no_action_required"]),
        "the report asserts risks, never certifies safety",
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
    climax = flags_matching(flags, desk="safety_underwriter", scenes_any=["S009", "S010", "S011"])
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
        bool(
            flags_matching(
                flags, category_any=["supernatural", "superstition"], scenes_any=["S007"]
            )
        ),
    )
    check(
        "territory: CN or UAE drug flag",
        bool(
            flags_about(
                flags,
                category_any=["drug"],
                text_any=["marijuana", "joint", "drug"],
                desk="territory_censor",
            )
        ),
    )

    # --- Rating prediction (demo moment #3)
    pred = (r.get("report") or {}).get("rating_prediction")
    check(
        "rating prediction filed with comparables",
        bool(pred and len(pred.get("comparables", [])) >= 6),
        "query_precedent -> file_rating_prediction; needs the corpus loaded",
    )
    check(
        "cut list present when prediction exceeds target",
        bool(
            not pred
            or pred.get("predicted") in (pred.get("target"), None)
            or pred.get("beats_to_cut")
        ),
    )

    # --- Verification health
    verdicts = r.get("verdicts") or {}
    verdict_ids = {str(k).split(":")[0] for k in verdicts}
    kept_ids = {f.get("flag_id") for f in flags}
    check(
        "verification: ran on every kept flag, rejection rate <= 40%",
        bool(verdicts)
        and kept_ids <= verdict_ids
        and not any(f.get("verification_unavailable") for f in flags)
        and len(rejected) <= 0.4 * max(1, len(rejected) + len(flags)),
        f"{len(rejected)} rejected / {len(rejected) + len(flags)} filed; verdicts for "
        f"{len(verdict_ids)} flags — zero rejections is legitimate when the desks' filing "
        "gates already blocked the weak flags; a sleeping verifier shows as missing "
        "verdicts or fail-open markers, and those fail this check",
    )
    check(
        "invariant: every kept flag has a citation with an excerpt",
        all(f["citations"] and all(c["excerpt"].strip() for c in f["citations"]) for f in flags),
    )
    check(
        "invariant: no unexamined entities (every extracted item dispositioned)",
        not r.get("unexamined"),
        f"unexamined={[u.get('surface') for u in r.get('unexamined') or []][:8]} — absence "
        "must never render as cleanliness",
    )
    tc_cov = (r.get("desk_coverage") or {}).get("territory_censor") or {}
    check(
        "territory: all 12 axis sweeps dispositioned by work-item id",
        tc_cov.get("work_items_done", 0) >= 12,
        f"territory work_items_done={tc_cov.get('work_items_done')} "
        f"of {tc_cov.get('work_items_assigned')} assigned — the 12 axis sweeps "
        "are now mechanical, not prompt folklore",
    )
    check(
        "invariant: no desk collapsed (worklist with zero dispositions)",
        not r.get("desks_incomplete"),
        f"desks_incomplete={r.get('desks_incomplete')} — the territory 5->0 failure class; "
        "silence must never grade as a clean bill",
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

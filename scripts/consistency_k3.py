#!/usr/bin/env python3
"""k-run self-consistency harness (Wave 2, A1-A3).

Runs the full pipeline k times on one script — triage included, so the runs
are genuinely independent and the capture-recapture math is honest — then
matches findings across runs, prints per-desk agreement, Krippendorff's
alpha, and the Chapman recall upper bound.

  .venv/bin/python scripts/consistency_k3.py [script] [k]

Cost: k full runs. Results land in runs/consistency_<stamp>.json.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from greenlight import pipeline  # noqa: E402
from greenlight.consistency import (  # noqa: E402
    alpha_with_clearances,
    krippendorff_alpha_binary,
    match_runs,
    recall_bound,
)

DESKS = ["clearance_counsel", "ratings_board", "safety_underwriter", "territory_censor"]


def main() -> int:
    script = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "fixtures" / "slack_tide.fountain")
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    records = []
    for i in range(k):
        print(f"=== pass {i + 1}/{k} ===", flush=True)
        t0 = time.time()
        rec = asyncio.run(pipeline.run(script))
        print(
            f"pass {i + 1}: {len(rec.get('flags', []))} flags, "
            f"{(time.time() - t0) / 60:.1f} min, error={rec.get('error')}",
            flush=True,
        )
        if rec.get("error"):
            print("pass errored — aborting the measurement (a dead run is not a sample)")
            return 1
        records.append(rec)
        # cli.py owns normal record-saving; the driver bypasses it, so persist
        # each pass here — offline reanalysis must never depend on memory
        ppath = ROOT / "runs" / f"k3_pass{i + 1}_{time.strftime('%Y%m%d_%H%M%S')}.json"
        ppath.write_text(json.dumps(rec, indent=2))

    match = match_runs(records)
    groups = match["groups"]
    hist = defaultdict(int)
    for g in groups:
        hist[g["agreement"]] += 1
    matrix = [[bool(v) for v in g["runs"]] for g in groups]
    alpha = krippendorff_alpha_binary(matrix)
    per_desk_alpha = {}
    for desk in DESKS:
        rows = [
            [bool(v) for v in g["runs"]]
            for g in groups
            if any(fid.split(":")[1][:2] in _desk_prefixes(desk) for fid in g["flag_ids"])
        ]
        per_desk_alpha[desk] = krippendorff_alpha_binary(rows) if rows else None
    rb = recall_bound(match)
    awc = alpha_with_clearances(records)

    out = {
        "script": script,
        "k": k,
        "union_size": match["union_size"],
        "fuzzy_merges": match["fuzzy_merges"],
        "agreement_histogram": dict(hist),
        "alpha_overall": alpha,
        "alpha_flag_vs_cleared": awc,
        "near_misses": match.get("near_misses", []),
        "alpha_per_desk": per_desk_alpha,
        "recall": rb,
        "groups": groups,
    }
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = ROOT / "runs" / f"consistency_{stamp}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\nunion {match['union_size']} findings | agreement {dict(hist)}")
    print(
        f"alpha (union-presence, floor-biased): {alpha:.3f}" if alpha is not None else "alpha: n/a"
    )
    a2 = awc["alpha"]
    print(
        f"alpha (flag-vs-cleared, {awc['rows_with_2plus_observations']} rated rows, "
        f"{awc['unanimous_rows']} unanimous): {a2:.3f}"
        if a2 is not None
        else "flag-vs-cleared alpha: n/a"
    )
    print(f"near misses to review: {len(match.get('near_misses', []))}")
    for d, a in per_desk_alpha.items():
        print(f"  {d}: {a:.3f}" if a is not None else f"  {d}: n/a")
    print(f"recall upper bound: {rb.get('recall_upper_bound')} (N-hat {rb.get('n_hat')})")
    print(f"saved: {path}")
    return 0


def _desk_prefixes(desk: str) -> tuple[str, ...]:
    return {
        "clearance_counsel": ("F1",),
        "ratings_board": ("F2",),
        "safety_underwriter": ("F3",),
        "territory_censor": ("F4",),
    }[desk]


if __name__ == "__main__":
    raise SystemExit(main())

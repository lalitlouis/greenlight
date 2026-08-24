#!/usr/bin/env python3
"""Produce a published case study from a screenplay we do not own.

The rule that makes this publishable: the script text never ships. The pipeline
runs locally on a study copy; the saved record is OUR analysis — findings with
web citations, scores, comparables — with the screenplay stripped: no source
path, no research dump, entity context truncated to short quotes. The site's
marked-up-script view is disabled for case records by construction (no script).

    python scripts/case_study.py .cache/case_scripts/clerks-1994.pdf \
        --slug clerks --title "Clerks" --year 1994 --target R \
        --hook "Rated NC-17 purely for language — overturned on appeal."
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT_CAP = 80  # chars of script quote kept per entity — commentary-scale


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--target", default="R")
    ap.add_argument("--hook", required=True)
    ap.add_argument("--clearance-budget", type=int, default=0,
                    help="Raise the clearance desk's research budget for entity-dense scripts")
    args = ap.parse_args()

    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from greenlight import pipeline
    from greenlight.pdf import screenplay_text

    src_path = Path(args.script)
    text = screenplay_text(src_path.name, src_path.read_bytes())
    tmp = ROOT / ".cache" / "case_scripts" / f"_{args.slug}.fountain"
    tmp.write_text(f"Title: {args.title}\nAuthor: (case study)\n\n{text}")

    budgets = None
    if args.clearance_budget:
        budgets = dict(pipeline.DEFAULT_BUDGETS, clearance_counsel=args.clearance_budget)
    record = asyncio.run(pipeline.run(tmp, target_rating=args.target, budgets=budgets))

    # --- strip: our analysis ships, the screenplay does not
    record["script_title"] = args.title
    record.pop("script_path", None)
    record.pop("research", None)
    for e in record.get("entities", []):
        if len(e.get("context", "")) > CONTEXT_CAP:
            e["context"] = e["context"][:CONTEXT_CAP].rstrip() + "…"
    record["kind"] = "case_study"
    record["case"] = {
        "title": args.title,
        "year": args.year,
        "hook": args.hook,
        "note": (
            "Independent analysis of a publicly circulating study draft, published for "
            "commentary and education. Not affiliated with the production. The screenplay "
            "text is not reproduced. Scores reflect the draft analyzed, not the released film."
        ),
    }

    out = ROOT / "runs" / f"case_{args.slug}.json"
    out.write_text(json.dumps(record, indent=2))
    rep = record.get("report") or {}
    print(
        f"{args.title}: score {rep.get('greenlight_score')}, "
        f"{len(record.get('flags', []))} findings, "
        f"prediction {(rep.get('rating_prediction') or {}).get('predicted')} "
        f"-> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Promote a completed live run into a published case study.

Usage: python scripts/promote_case.py RUN_ID --slug the-social-network \
         --title "The Social Network" --year 2010 --hook "..."

Applies the same stripping rules as case_study.py: the analysis ships, the
screenplay does not (no research blob, no script path, entity contexts capped),
plus the standard commentary/education note.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT_CAP = 160


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--hook", required=True)
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT / "src"))
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from greenlight import storage

    record = storage.load_record(args.run_id)
    if record is None:
        print(f"no record for {args.run_id}", file=sys.stderr)
        return 1
    if record.get("error"):
        print(f"refusing: run has error {record['error']!r}", file=sys.stderr)
        return 1

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
    out = ROOT / "runs" / f"case_{args.slug.replace('-', '_')}.json"
    out.write_text(json.dumps(record, indent=2))
    rep = record.get("report") or {}
    print(
        f"{args.title}: score {rep.get('greenlight_score')}, "
        f"{len(record.get('flags', []))} findings -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

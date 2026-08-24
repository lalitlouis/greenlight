"""CLI entry point: python -m greenlight.cli run fixtures/slack_tide.fountain"""

from __future__ import annotations

import argparse
import asyncio
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="greenlight")
    sub = ap.add_subparsers(dest="cmd", required=True)
    runp = sub.add_parser("run", help="Run the pipeline on a screenplay.")
    runp.add_argument("script", help="Path to a .fountain screenplay")
    runp.add_argument(
        "--budget",
        type=int,
        default=0,
        help="Uniform per-desk research() cap (0 = per-desk defaults)",
    )
    runp.add_argument("--no-save", action="store_true", help="Do not write runs/<ts>.json")
    runp.add_argument("--target", default="PG-13", help="Target MPA rating for the prediction")
    wp = sub.add_parser("write", help="Writer's Room: coverage, pitch package, format check.")
    wp.add_argument("script", help="Path to a .fountain screenplay")
    args = ap.parse_args(argv)

    if args.cmd == "write":
        import json

        from greenlight.writer import pipeline as writer_pipeline

        record = asyncio.run(writer_pipeline.run(args.script))
        path = writer_pipeline.save_run(record)
        cov = record.get("coverage") or {}
        print(json.dumps({k: record[k] for k in ("script_title", "elapsed_s", "error")}, indent=2))
        print("verdict:", cov.get("verdict"), "-", (cov.get("verdict_reason") or "")[:200])
        print("comps:", [c["title"] for c in (record.get("pitch") or {}).get("comps", [])])
        print("saved:", path)
        return 0

    from greenlight import pipeline

    budgets = dict.fromkeys(pipeline.DEFAULT_BUDGETS, args.budget) if args.budget else None
    record = asyncio.run(pipeline.run(args.script, budgets=budgets, target_rating=args.target))
    pipeline.print_summary(record)
    if not args.no_save:
        path = pipeline.save_run(record)
        print(f"\nrun saved: {path}")
    return 0 if record["flags"] else 1


if __name__ == "__main__":
    sys.exit(main())

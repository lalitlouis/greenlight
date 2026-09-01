#!/usr/bin/env python3
"""Regenerate ALL published case studies with case-grade research budgets.

Case studies are showcase content: nothing in them may go unresearched, so they
run with budgets far above the normal per-run scaling (which stays unchanged
for regular users). Preserves each case's curated hook/year/slug; applies the
same stripping rules as case_study.py. Sequential, and waits politely if a
live user run is in flight (shared quota).

Usage: python scripts/regen_case_studies.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from greenlight import pipeline, storage  # noqa: E402

CONTEXT_CAP = 160
CASE_BUDGETS = {
    "clearance_counsel": 180,
    "ratings_board": 16,
    "safety_underwriter": 24,
    "territory_censor": 24,
}

# slug -> (source: cache filename OR gcs run id, target rating)
CASES = {
    # "reservoir_dogs": ("_reservoir_dogs.fountain", "R"),  # done 2026-09-01 02:45
    "clerks": ("_clerks.fountain", "R"),
    "little_miss_sunshine": ("_little_miss_sunshine.fountain", "R"),
    "the_social_network": ("gcs:2bec8312bc50", "PG-13"),
    "the_wolf_of_wall_street": ("gcs:a1d513afaad9", "R"),
    "the_hangover": ("gcs:13dfdcf2f1d4", "R"),
}


CASE_TIMEOUT_S = 35 * 60  # a stalled model/API call must fail loudly, not hang the batch


async def _run_case_with_timeout(path, target, title):
    return await asyncio.wait_for(
        pipeline.run(path, budgets=dict(CASE_BUDGETS), target_rating=target, title_hint=title),
        timeout=CASE_TIMEOUT_S,
    )


def wait_for_quiet() -> None:
    while True:
        try:
            with urllib.request.urlopen("https://scriptrisk.com/api/metrics-lite", timeout=10) as r:
                if json.load(r).get("running_now", 0) == 0:
                    return
        except Exception:
            return
        print("  live user run in flight — waiting 120s (shared quota)...")
        time.sleep(120)


def main() -> int:  # noqa: PLR0915, PLR0912 - a linear per-case sequence
    failures = []
    for slug, (src, target) in CASES.items():
        out = ROOT / "runs" / f"case_{slug}.json"
        existing = json.loads(out.read_text()) if out.exists() else {}
        case_meta = existing.get("case") or {}
        title = case_meta.get("title") or slug.replace("_", " ").title()

        cached = ROOT / ".cache" / "case_scripts" / f"_{slug}.fountain"
        if src.startswith("gcs:") and cached.exists():
            # a prior regen already materialized the script locally — the GCS
            # run id may be long-deleted (all three were, 2026-09-01)
            path = cached
        elif src.startswith("gcs:"):
            text = storage.load_script(src[4:])
            if not text:
                print(f"{slug}: MISSING script in GCS — skipped")
                continue
            path = ROOT / ".cache" / "case_scripts" / f"_{slug}.fountain"
            if not text.lstrip().startswith("Title:"):
                text = f"Title: {title}\nAuthor: (case study)\n\n" + text
            path.write_text(text)
        else:
            path = ROOT / ".cache" / "case_scripts" / src

        wait_for_quiet()
        print(f"=== {title}: running with case budgets {CASE_BUDGETS} ===")
        t0 = time.time()
        record = None
        for attempt in (1, 2):
            try:
                record = asyncio.run(_run_case_with_timeout(path, target, title))
                break
            except TimeoutError:
                print(
                    f"{slug}: TIMEOUT after {CASE_TIMEOUT_S // 60} min (attempt {attempt}) — "
                    + ("retrying once" if attempt == 1 else "giving up, existing case kept"),
                    flush=True,
                )
            except Exception as exc:  # one case's bug must not kill the batch
                # (a ContractViolation at report build killed the whole batch
                # after Clerks' full paid analysis, 2026-09-01)
                print(
                    f"{slug}: CRASH {type(exc).__name__}: {exc} — existing case kept",
                    flush=True,
                )
                break
        if record is None:
            failures.append(slug)
            continue
        mins = (time.time() - t0) / 60
        if record.get("error"):
            print(f"{slug}: RUN ERROR {record['error']!r} — existing case kept")
            continue

        record["script_title"] = title
        record.pop("script_path", None)
        record.pop("research", None)
        for e in record.get("entities", []):
            if len(e.get("context", "")) > CONTEXT_CAP:
                e["context"] = e["context"][:CONTEXT_CAP].rstrip() + "…"
        record["kind"] = "case_study"
        record["case"] = case_meta or {"title": title, "year": None, "hook": "", "note": ""}
        out.write_text(json.dumps(record, indent=2))

        rep = record.get("report") or {}
        oq = [q for qs in (record.get("open_questions") or {}).values() for q in qs]
        budget_leak = sum(1 for q in oq if "budget" in str(q).lower())
        print(
            f"{slug}: score {rep.get('greenlight_score')}, {len(record.get('flags', []))} flags, "
            f"{len(record.get('rejected_flags', []))} rejected, "
            f"rating {(rep.get('rating_prediction') or {}).get('predicted')}, "
            f"open questions {len(oq)} (budget-phrased: {budget_leak}), {mins:.1f} min"
        )
    if failures:
        print(f"FAILED CASES: {', '.join(failures)}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Offline contrastive-case checks; optionally grade a saved, matching live run.

Never calls a model or retrieval service. An offline PASS checks the parser and
census only. Saved-run checks screen categories/verification; semantic review
and professional validation of the expected outcomes remain separate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from greenlight.parser import parse_fountain  # noqa: E402
from greenlight.prepass import f_word_inventory, spoken_f_words  # noqa: E402

CASES = ROOT / "fixtures" / "accuracy" / "contrastive_cases.json"


def inventory_errors(case: dict[str, Any]) -> list[str]:
    _, scenes = parse_fountain(case["script"])
    inventory = f_word_inventory(scenes)
    errors = []
    if len(scenes) != 1:
        errors.append("Expected one anchored scene")
    for channel in ("dialogue", "action"):
        actual = len(inventory[channel])
        if actual != case[f"{channel}_f_words"]:
            errors.append(f"{channel}: expected {case[f'{channel}_f_words']}, got {actual}")
    if spoken_f_words(scenes) != case["dialogue_f_words"]:
        errors.append("Spoken-count rule input disagrees with dialogue inventory")
    return errors


def record_errors(case: dict[str, Any], record: dict[str, Any]) -> list[str]:
    """Screen a saved case run without misrepresenting a different draft as tested."""
    expected_hash = hashlib.sha256(case["script"].encode()).hexdigest()
    if (record.get("draft") or {}).get("sha256") != expected_hash:
        return ["Wrong/missing draft hash: this record does not evaluate the case"]
    errors = []
    if "error" not in record or record["error"]:
        errors.append("Run did not record successful completion")
    if record.get("desks_incomplete") or record.get("unexamined"):
        errors.append("Run has incomplete desk coverage")
    report = record.get("report") or {}
    if not report or report.get("verification_degraded"):
        errors.append("Missing report or degraded verification")
    flags = report.get("flags") or []
    desk_flags = [f for f in flags if f.get("agent") == case["desk"]]
    categories = {f.get("category") for f in desk_flags}
    errors.extend(
        f"Expected finding absent: {category}"
        for category in case["required_categories"]
        if category not in categories
    )
    errors.extend(
        f"Unexpected finding: {category}"
        for category in case["forbidden_categories"]
        if category in categories
    )
    for flag in flags:
        verdict = (record.get("verdicts") or {}).get(flag["flag_id"]) or {}
        if (
            verdict.get("verdict") not in {"SUPPORTED", "PARTIAL"}
            or verdict.get("fail_open")
            or flag.get("verification_unavailable")
        ):
            errors.append(f"Unverified finding: {flag['flag_id']}")
        if not any(c.get("excerpt") for c in flag.get("citations") or []):
            errors.append(f"Uncited finding: {flag['flag_id']}")
        if flag.get("agent") == "safety_underwriter" and flag.get("severity") == "BLOCKER":
            errors.append(f"Safety BLOCKER without confirmed production facts: {flag['flag_id']}")
    pred = report.get("rating_prediction") or {}
    if case["desk"] == "ratings_board" and pred.get("spoken_f_words") != case["dialogue_f_words"]:
        errors.append("Prediction's spoken count disagrees with the case")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", help="Case ID to export or grade")
    ap.add_argument("--export", type=Path, help="Write the selected original Fountain script")
    ap.add_argument("--record", type=Path, help="Grade a saved live run of the selected case")
    args = ap.parse_args()
    data = json.loads(CASES.read_text())
    cases = data["cases"]
    if (args.export or args.record) and not args.case:
        ap.error("--export and --record require --case")
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            ap.error("Unknown case ID")
    if args.export:
        args.export.write_text(cases[0]["script"])
        print(f"Exported {cases[0]['id']} to {args.export}; no live analysis started")
    failed = 0
    for case in cases:
        errors = inventory_errors(case)
        if args.record:
            errors += record_errors(case, json.loads(args.record.read_text()))
        print(f"{'FAIL' if errors else 'PASS'} {case['id']}")
        for error in errors:
            print(f"  {error}")
        failed += bool(errors)
    print(f"{len(cases) - failed}/{len(cases)} cases passed deterministic checks")
    print("Desk accuracy is NOT measured by the offline inventory checks.")
    print(f"Label status: {data['review_status']}")
    if args.record:
        print("Human review still required:")
        for expectation in cases[0]["review_expectations"]:
            print(f"  - {expectation}")
    return int(bool(failed))


if __name__ == "__main__":
    sys.exit(main())

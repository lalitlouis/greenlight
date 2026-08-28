#!/usr/bin/env python3
"""Structure BBFC cutsSummary records into the cut-simulator validation set.

Each record: (title, classification-achieved, cuts prose, whether the cut was
company-elected vs compulsory, and — when the prose names it — the uncut
category that was available). This is a regulator's own record of which
changes moved the band.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / ".cache" / "ratings_ingest" / "bbfc.jsonl"
OUT = ROOT / ".cache" / "ratings_ingest" / "bbfc_cuts.json"

_UNCUT = re.compile(r"uncut\s+'?\"?(U|PG|12A|12|15|18|R18)\b", re.I)
_ELECTED = re.compile(r"\b(company|distributor)\s+(?:chose|opted|elected|requested)", re.I)
_CATEGORY_FOR = re.compile(
    r"(?:achie?ve|obtain|secure|receive)[^.]{0,30}'?\"?(U|PG|12A|12|15|18)\b", re.I
)
_WHAT = re.compile(
    r"remove[sd]?\s+(?:a number of\s+)?(?:uses of\s+)?([^.;]{4,80})"
    r"|reduc(?:e|tion)[s]?\s+(?:of|to|in)\s+([^.;]{4,80})",
    re.I,
)


def main() -> int:
    rows = [json.loads(line) for line in SRC.read_text().splitlines() if line.strip()]
    cuts = []
    for r in rows:
        b = r.get("bbfc") or {}
        cs = b.get("cutsSummary")
        if not cs:
            continue
        uncut = _UNCUT.search(cs)
        target = _CATEGORY_FOR.search(cs)
        what = _WHAT.search(cs)
        cuts.append(
            {
                "title": r["title"],
                "year": r["year"],
                "us_rating": r.get("us_rating"),
                "classification": b.get("classification"),
                "elected": bool(_ELECTED.search(cs)),
                "uncut_category_available": uncut.group(1) if uncut else None,
                "target_category": target.group(1) if target else b.get("classification"),
                "what_was_cut": next((g for g in (what.groups() if what else []) if g), None),
                "cut_duration_s": b.get("cutDurationSeconds"),
                "raw": cs,
            }
        )
    elected = sum(1 for c in cuts if c["elected"])
    with_delta = sum(1 for c in cuts if c["uncut_category_available"])
    print(
        f"{len(cuts)} cuts records | {elected} company-elected | "
        f"{with_delta} state the uncut category (the band delta)"
    )
    moves = Counter(
        (c["uncut_category_available"], c["target_category"])
        for c in cuts
        if c["uncut_category_available"] and c["target_category"]
    )
    for (frm, to), n in moves.most_common(10):
        print(f"  {frm} -> {to}: {n}")
    OUT.write_text(json.dumps(cuts, indent=1))
    print(f"saved: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

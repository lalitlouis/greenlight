"""The binder is a faithful projection of the report — asserted, not hoped.

Confirmed failure modes this gate exists to prevent (2026-08-27 review):
a territory fold silently dropped finding F403; the header claimed one more
MEDIUM than the table rendered; six cells were sliced mid-word; Item
duplicated Category on every desk row without an entity.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pytest

from greenlight import binder

ROOT = Path(__file__).resolve().parents[1]
RECORDS = sorted(glob.glob(str(ROOT / "runs" / "case_*.json")))


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text())


@pytest.mark.parametrize("path", RECORDS, ids=[Path(p).stem for p in RECORDS])
def test_binder_matches_report(path: str) -> None:
    record = _load(path)
    b = binder.build(record, {})
    rows = [r for r in b["rows"] if r["Finding"]]

    cited = [f for f in record.get("flags", []) if f.get("citations")]
    by_id = {f["flag_id"]: f for f in cited}

    # Every kept finding renders exactly once; nothing extra appears.
    rendered_ids = [r["Finding"] for r in rows]
    assert sorted(rendered_ids) == sorted(by_id), (
        f"binder rows diverge from report findings in {Path(path).name}"
    )
    assert len(rendered_ids) == len(set(rendered_ids)), "a finding rendered twice"

    for r in rows:
        f = by_id[r["Finding"]]
        # Severity and cost are copied, never re-derived.
        assert r["Severity"] == f.get("severity", "")
        cost = (f.get("remedy") or {}).get("est_cost_usd") or []
        if len(cost) == 2 and all(isinstance(c, (int, float)) for c in cost) and cost[1] > 0:
            assert str(f"{cost[0]:,.0f}").split(".")[0].replace(",", "") in r[
                "Est. cost (USD)"
            ].replace(",", ""), f"cost range missing for {r['Finding']}"
        # The finding text (where corrected titles live) is present in the note.
        if f.get("finding"):
            head = str(f["finding"])[:60]
            assert head in r["Remedy / licensing note"], (
                f"finding text absent from binder note for {r['Finding']}"
            )
        # No mid-word slice: a clipped cell ends with the ellipsis marker.
        note = r["Remedy / licensing note"]
        assert len(note) <= 620 or note.endswith("…")
        # Item never silently duplicates Category.
        if r["Item"] != "—":
            assert r["Item"] != r["Category"]

    # The header counts describe this table, not some other artifact.
    from collections import Counter

    assert b["counts"] == dict(Counter(r["Severity"] for r in rows if r["Severity"]))


def test_at_least_one_record_present() -> None:
    assert RECORDS, "no case records found — the gate is vacuously passing"

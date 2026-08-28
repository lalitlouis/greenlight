#!/usr/bin/env python3
"""Backfill scene_meta and draft identity into existing case records.

New records carry these from the pipeline; case records generated before the
change get them injected from their cached sources so the binder's PAGE and
SCENE HEADING columns populate and the draft-identity block renders.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from greenlight import parser  # noqa: E402


def main() -> int:
    for rec_path in sorted((ROOT / "runs").glob("case_*.json")):
        slug = rec_path.stem.removeprefix("case_")
        src_path = ROOT / ".cache" / "case_scripts" / f"_{slug}.fountain"
        if not src_path.exists():
            print(f"{slug}: no cached source — skipped")
            continue
        record = json.loads(rec_path.read_text())
        source = src_path.read_text()
        meta, scenes = parser.parse_fountain(source)
        record["scene_meta"] = {
            sc["scene_id"]: {
                "heading": sc.get("heading", ""),
                "page": sc.get("page", ""),
                "number": sc.get("number", ""),
            }
            for sc in scenes
        }
        record.setdefault(
            "draft",
            parser.draft_identity(source, meta, scenes, record.get("script_title") or slug),
        )
        rec_path.write_text(json.dumps(record, indent=2))
        print(
            f"{slug}: scene_meta for {len(scenes)} scenes, draft {record['draft']['sha256'][:12]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

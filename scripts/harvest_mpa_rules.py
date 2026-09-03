#!/usr/bin/env python3
"""Harvest the MPA "Classification and Rating Rules" into a checked-in asset.

The desks may cite a rating RULE only from the MPA's own text — the corpus measures
what CARA did, the rules say what CARA requires. One official document, one-time
download, provenance per section; `rating_rules()` in the toolbelt serves it.

Usage: python scripts/harvest_mpa_rules.py [local.pdf]
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "greenlight" / "data" / "mpa_rating_rules.json"
URL = "https://www.filmratings.com/wp-content/uploads/2025/08/rating_rules.pdf"
_FOOTER = re.compile(r"^(?:\d+|Classification and Rating Rules Effective [A-Za-z]+ \d+, \d{4})$")
_CAT = re.compile(r"\((\d)\)\s+(G|PG|PG-13|R|NC-17)\s+-\s+")


def _clean(block: str) -> str:
    lines = [ln.strip() for ln in block.splitlines()]
    lines = [ln for ln in lines if ln and not _FOOTER.match(ln)]
    return " ".join(lines)


def main() -> int:
    if len(sys.argv) > 1:
        data = Path(sys.argv[1]).read_bytes()
    else:
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=60).read()
    from io import BytesIO

    import pdfplumber

    with pdfplumber.open(BytesIO(data)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    eff = re.search(r"Effective as revised ([A-Za-z]+ \d+, \d{4})", text)
    marks = list(_CAT.finditer(text))
    assert len(marks) >= 5, f"expected the five rating categories, found {len(marks)}"
    sections = []
    for i, m in enumerate(marks[:5]):
        end = marks[i + 1].start() if i + 1 < len(marks) else text.find("Section", m.end())
        block = text[m.start() : end if end > 0 else m.end() + 3000]
        # the paragraph runs until the next Section/ARTICLE heading after NC-17
        if i == 4:
            stop = re.search(r"\n(?:Section \d+\.|ARTICLE [IVX]+)", block)
            block = block[: stop.start()] if stop else block
        sections.append(
            {"id": f"rating_{m.group(2)}", "title": _clean(block)[:80], "text": _clean(block)}
        )
    pg13 = next(s for s in sections if s["id"] == "rating_PG-13")
    rule = re.search(
        r"A motion picture's single use of one of the harsher sexually-derived words.*?"
        r"inconspicuous\.",
        pg13["text"],
    )
    assert rule, "expletive rule sentences not found"
    sections.append(
        {
            "id": "pg13_expletive_rule",
            "title": "PG-13 — the harsher sexually-derived expletive rule",
            "text": rule.group(0),
        }
    )
    asset = {
        "source": URL,
        "document": "Classification and Rating Rules (Motion Picture Association / NATO)",
        "effective": eff.group(1) if eff else None,
        "sha256": hashlib.sha256(data).hexdigest(),
        "harvested_at": dt.date.today().isoformat(),
        "sections": sections,
    }
    OUT.write_text(json.dumps(asset, indent=2, ensure_ascii=False) + "\n")
    for s in sections:
        print(f"{s['id']:22} {len(s['text']):5} chars | {s['text'][:90]}")
    print(f"wrote {OUT} (effective {asset['effective']}, sha256 {asset['sha256'][:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

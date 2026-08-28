#!/usr/bin/env python3
"""Harvest BBFC classification records for the corpus films.

Each release page embeds __NEXT_DATA__ JSON: classification, shortFormInsight
(descriptors), cutsSummary (compulsory vs company-elected cuts — a regulator's
own record of which changes moved the band), cut duration, and reference id.
Two polite requests per film (search -> release). Resumable.
Writes .cache/ratings_ingest/bbfc.jsonl.
"""

from __future__ import annotations

import difflib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / ".cache" / "ratings_ingest" / "corpus.jsonl"
OUT = ROOT / ".cache" / "ratings_ingest" / "bbfc.jsonl"

NEXT_DATA = re.compile(r'__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
HDRS = {"User-Agent": "ScriptRisk-research/1.0 (one-time corpus enrichment)"}
_FUZZY = 0.9
_KEEP = [
    "title",
    "classification",
    "shortFormInsight",
    "cutsSummary",
    "VMCutsInfo",
    "cutDurationSeconds",
    "durationSeconds",
    "version",
    "bbfcReference",
    "releaseType",
]


def fetch(url: str) -> str:
    delay = 3.0
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers=HDRS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    return ""


def next_data(html: str) -> dict:
    m = NEXT_DATA.search(html)
    return json.loads(m.group(1)) if m else {}


def norm(t: str) -> str:
    t = re.sub(r"\(\d{4}\)$", "", t.strip().lower()).strip()
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def search(title: str) -> list[dict]:
    q = urllib.parse.quote(title)
    d = next_data(fetch(f"https://www.bbfc.co.uk/search?q={q}"))
    res = d.get("props", {}).get("pageProps", {}).get("searchResults", {}).get("results", [])
    return [r for r in res if r.get("dataType") == "release" and r.get("slug")]


def best(title: str, year: int, hits: list[dict]) -> dict | None:
    want = norm(title)
    scored = []
    for h in hits:
        ratio = difflib.SequenceMatcher(None, want, norm(h.get("title", ""))).ratio()
        year_off = 0
        m = re.search(r"\((\d{4})\)", h.get("title", ""))
        date = h.get("date") or ""
        hit_year = int(m.group(1)) if m else int(date[:4]) if date[:4].isdigit() else None
        if hit_year is not None:
            year_off = min(abs(hit_year - year), 5)
        scored.append((ratio - 0.02 * year_off, ratio, h))
    scored.sort(key=lambda x: x[0], reverse=True)
    if scored and scored[0][1] >= _FUZZY:
        return scored[0][2]
    return None


def release(slug: str) -> dict:
    d = next_data(fetch("https://www.bbfc.co.uk" + slug))
    rel = d.get("props", {}).get("pageProps", {}).get("release", {}) or {}
    return {k: rel.get(k) for k in _KEEP if rel.get(k) not in (None, "", 0)}


def main() -> int:
    rows = [json.loads(line) for line in CORPUS.read_text().splitlines() if line.strip()]
    done: set[str] = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                if not d.get("error"):
                    done.add(d["title"])
    found = 0
    with OUT.open("a") as out:
        for i, r in enumerate(rows):
            if r["title"] in done:
                continue
            entry = {
                "title": r["title"],
                "year": r["year"],
                "us_rating": r["rating"],
                "source": "bbfc.co.uk release pages",
                "harvested_at": time.strftime("%Y-%m-%d"),
            }
            try:
                hit = best(r["title"], r["year"], search(r["title"]))
                if hit:
                    entry["bbfc"] = release(hit["slug"])
                    entry["slug"] = hit["slug"]
            except Exception as exc:
                entry["error"] = str(exc)[:80]
            out.write(json.dumps(entry) + "\n")
            out.flush()
            found += "bbfc" in entry
            if i % 100 == 0:
                print(f"...{i}/{len(rows)}, {found} matched", flush=True)
            time.sleep(0.7)
    print(f"done: {found} BBFC records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

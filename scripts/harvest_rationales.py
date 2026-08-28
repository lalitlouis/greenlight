#!/usr/bin/env python3
"""Harvest official CARA rating rationales from filmratings.com search results.

The /search-results/ page renders server-side — plain HTTP, no JS. One polite
request per corpus film (0.7s spacing, backoff on throttle), resumable.
Writes .cache/ratings_ingest/rationales.jsonl.

Discovery notes: Wikipedia leads carry 3/6302 rationales and article bodies
none; Wikidata has no rationale property. filmratings.com is the authority.
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
OUT = ROOT / ".cache" / "ratings_ingest" / "rationales.jsonl"

TITLE = re.compile(r'<div class="item-title">([^<]+)</div>')
REASON = re.compile(r'Reason: </span>\s*<span class="text">([^<]+)</span>')
RATED = re.compile(r"Rated\s+(G|PG-13|PG|R|NC-17)\b")
HDRS = {"User-Agent": "ScriptRisk-research/1.0 (one-time corpus enrichment)"}
_FUZZY = 0.92


def norm_title(t: str) -> str:
    t = t.strip().lower()
    # CARA inverts articles: "Social Network, The" -> "the social network"
    m = re.match(r"^(.*),\s*(the|a|an)$", t)
    if m:
        t = f"{m.group(2)} {m.group(1)}"
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


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


def search(title: str, year: int | None) -> list[tuple[str, str]]:
    q = urllib.parse.quote(title)
    url = f"https://www.filmratings.com/search-results/?search={q}"
    if year:
        url += f"&my={year}"
    html = fetch(url)
    out = []
    # segment per entry: title -> everything until the next title holds its reason
    parts = TITLE.split(html)
    for i in range(1, len(parts), 2):
        fr_title, body = parts[i].strip(), parts[i + 1]
        m = REASON.search(body)
        if m:
            out.append((fr_title, m.group(1).strip()))
    return out


def best_match(title: str, entries: list[tuple[str, str]]) -> tuple[str, str] | None:
    want = norm_title(title)
    for fr_title, reason in entries:
        if norm_title(fr_title) == want:
            return (fr_title, reason)
    scored = [
        (difflib.SequenceMatcher(None, want, norm_title(ft)).ratio(), ft, r) for ft, r in entries
    ]
    scored.sort(reverse=True)
    if scored and scored[0][0] >= _FUZZY:
        return (scored[0][1], scored[0][2])
    return None


def main() -> int:
    rows = [json.loads(line) for line in CORPUS.read_text().splitlines() if line.strip()]
    done: dict[str, dict] = {}
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                if not d.get("error"):
                    done[d["title"]] = d
    found = sum(1 for d in done.values() if d.get("rationale"))
    with OUT.open("a") as out:
        for i, r in enumerate(rows):
            if r["title"] in done:
                continue
            entry = {
                "title": r["title"],
                "year": r["year"],
                "rating": r["rating"],
                "rationale": None,
            }
            try:
                # CARA's "year rated" can differ from release year by one
                hits = (
                    search(r["title"], r["year"])
                    or search(r["title"], r["year"] - 1)
                    or search(r["title"], None)
                )
                match = best_match(r["title"], hits)
                if match:
                    fr_title, reason = match
                    entry["fr_title"] = fr_title
                    entry["rationale"] = reason
                    m = RATED.search(reason)
                    if m and m.group(1) != r["rating"]:
                        entry["rating_in_text"] = m.group(1)
            except Exception as exc:
                entry["error"] = str(exc)[:80]
            out.write(json.dumps(entry) + "\n")
            out.flush()
            found += bool(entry.get("rationale"))
            if i % 100 == 0:
                print(f"...{i}/{len(rows)}, {found} rationales", flush=True)
            time.sleep(0.7)
    print(f"done: {found} rationales")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

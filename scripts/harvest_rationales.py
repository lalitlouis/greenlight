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
FIELD = re.compile(
    r'<span class="label">([^<:]+):\s*</span>\s*<span class="text">\s*([^<]*?)\s*</span>', re.S
)
STUDIO = re.compile(r'<div class="studio">\s*([^<]*?)\s*</div>', re.S)
RATED = re.compile(r"Rated\s+(G|PG-13|PG|R|NC-17)\b")
HDRS = {"User-Agent": "ScriptRisk-research/1.0 (one-time corpus enrichment)"}
_FUZZY = 0.92


def norm_title(t: str) -> str:
    import html as _html

    t = _html.unescape(t).strip().lower()
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
    # segment per entry: title -> everything until the next title holds its fields
    parts = TITLE.split(html)
    for i in range(1, len(parts), 2):
        fr_title, body = parts[i].strip(), parts[i + 1]
        fields = {k.strip().lower(): v.strip() for k, v in FIELD.findall(body)}
        if not fields.get("reason"):
            continue
        sm = STUDIO.search(body)
        known = {"reason", "year rated", "certificate #", "alternate titles"}
        out.append(
            {
                "fr_title": fr_title,
                "reason": fields["reason"],
                "year_rated": fields.get("year rated", ""),
                "certificate": fields.get("certificate #", ""),
                "alternate_titles": fields.get("alternate titles", ""),
                "studio": sm.group(1).strip() if sm else "",
                "extra": {k: v for k, v in fields.items() if k not in known},
            }
        )
    return out


def best_match(
    title: str, entries: list[dict], year: int | None = None, rating: str | None = None
) -> dict | None:
    want = norm_title(title)
    if rating and len(entries) > 1:
        # two same-title films (Titanic 1997 x2): the corpus rating letter votes
        lettered = [e for e in entries if (m := RATED.search(e["reason"])) and m.group(1) == rating]
        if lettered:
            entries = lettered
    if year and len(entries) > 1:

        def _dist(e: dict) -> int:
            try:
                return abs(int(e.get("year_rated") or 0) - year)
            except ValueError:
                return 99

        entries = sorted(entries, key=_dist)
    for e in entries:
        names = [e["fr_title"], *e.get("alternate_titles", "").split(",")]
        if any(norm_title(n) == want for n in names if n.strip()):
            return e
    scored = sorted(
        (
            (difflib.SequenceMatcher(None, want, norm_title(e["fr_title"])).ratio(), i)
            for i, e in enumerate(entries)
        ),
        reverse=True,
    )
    if scored and scored[0][0] >= _FUZZY:
        return entries[scored[0][1]]
    return None


def _apply_match(entry: dict, match: dict, hits: list[dict], corpus_rating: str) -> None:
    same_title = [e for e in hits if norm_title(e["fr_title"]) == norm_title(match["fr_title"])]
    if len(same_title) > 1:
        # multiple certificates on one title = a rating EVENT trail
        # (resubmissions, edited versions) — the cut simulator's closest
        # public ground truth; flagged as a cohort for B2 validation
        entry["all_certs"] = [
            {
                "certificate": e["certificate"],
                "year_rated": e["year_rated"],
                "reason": e["reason"],
                "studio": e["studio"],
            }
            for e in same_title
        ]
    entry["fr_title"] = match["fr_title"]
    entry["rationale"] = match["reason"]  # verbatim, unparsed
    entry["year_rated"] = match["year_rated"]
    entry["certificate"] = match["certificate"]
    entry["studio"] = match["studio"]
    m = RATED.search(match["reason"])
    if m and m.group(1) != corpus_rating:
        entry["rating_in_text"] = m.group(1)


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
                "source": "filmratings.com search-results",
                "harvested_at": time.strftime("%Y-%m-%d"),
            }
            try:
                # CARA's "year rated" can differ from release year by one
                hits = (
                    search(r["title"], r["year"])
                    or search(r["title"], r["year"] - 1)
                    or search(r["title"], None)
                )
                match = best_match(r["title"], hits, r["year"], r["rating"])
                if match:
                    twins = [
                        e
                        for e in hits
                        if e is not match
                        and norm_title(e["fr_title"]) == norm_title(match["fr_title"])
                        and e.get("year_rated") == match.get("year_rated")
                    ]
                    if twins:
                        entry["ambiguous_certs"] = [
                            match["certificate"],
                            *(t["certificate"] for t in twins),
                        ]
                if match:
                    _apply_match(entry, match, hits, r["rating"])
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

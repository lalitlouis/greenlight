#!/usr/bin/env python3
"""Ratings-corpus ingest: the content-profile corpus for the Ratings Board desk.

Provenance per docs/DATA_SOURCES.md (approved 2026-08-24): film list + official
MPA rating from Wikidata (P1657, CC0) via SPARQL; each film's CONTENT PROFILE —
article lead + plot section — from the official MediaWiki API. The pilot proved
CARA rationale strings are absent from Wikipedia prose (1% hit rate), so the kNN
runs over content profiles, which carry a richer signal anyway. One source_url
per row; every comparable in a report is itself citable.

    python scripts/ingest_ratings.py pilot [N]    # the original rationale-rate pilot
    python scripts/ingest_ratings.py fetch [N]    # film list + article text -> .cache
    python scripts/ingest_ratings.py load         # embed (Vertex) + insert (ClickHouse)
    python scripts/ingest_ratings.py query "..."  # smoke-test kNN end to end
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = "GREENLIGHT-corpus-pilot/0.1 (https://github.com/lalitlouis/greenlight)"
SPARQL = "https://query.wikidata.org/sparql"
WIKI_API = "https://en.wikipedia.org/w/api.php"
CACHE = Path(__file__).resolve().parents[1] / ".cache" / "ratings_ingest"

RATINGS = ("G", "PG", "PG-13", "R", "NC-17")

# "rated R for strong brutal violence..." / "received a PG-13 rating for ..." /
# "rated R by the MPAA for ..." — the CARA descriptor is the "for ..." clause.
_PATTERNS = [
    re.compile(
        r"\brated\s+(PG-13|NC-17|PG|G|R)\b[^.\n]{0,80}?\bfor\s+([^.\n]{10,220})", re.IGNORECASE
    ),
    re.compile(
        r"\b(PG-13|NC-17|PG|G|R)\s+rating\b[^.\n]{0,60}?\bfor\s+([^.\n]{10,220})", re.IGNORECASE
    ),
    re.compile(
        r"\b(PG-13|NC-17|PG|G|R)\b\s*(?:certificate|rating)?\s*\bfor\s+([^.\n]{10,220})",
        re.IGNORECASE,
    ),
]


def _get(url: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}?{qs}", headers={"User-Agent": UA, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def fetch_film_list(limit: int) -> list[dict]:
    """Top films (by Wikidata sitelink count, a popularity proxy) carrying an MPA rating."""
    query = f"""
    SELECT ?film ?ratingLabel ?year ?title ?links WHERE {{
      {{ SELECT ?film ?links WHERE {{
           ?film wdt:P1657 [] ; wikibase:sitelinks ?links .
         }} ORDER BY DESC(?links) LIMIT {limit * 4} }}
      ?film wdt:P1657 ?rating .
      ?article schema:about ?film ;
               schema:isPartOf <https://en.wikipedia.org/> ;
               schema:name ?title .
      OPTIONAL {{ ?film wdt:P577 ?date . }}
      BIND(YEAR(?date) AS ?year)
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """
    data = _get(SPARQL, {"query": query, "format": "json"})
    seen, films = set(), []
    for row in data["results"]["bindings"]:
        title = row["title"]["value"]
        rating = row["ratingLabel"]["value"].replace("MPAA ", "").replace(" (MPAA)", "").strip()
        # Wikidata labels vary ("R", "PG-13 (USA)", ...) — normalize to the bare mark.
        m = re.search(r"\b(PG-13|NC-17|PG|G|R)\b", rating)
        year = int(row["year"]["value"]) if "year" in row else 0
        # The MPA rating system began in 1968 — the corpus is the complete era.
        if not m or title in seen or year < 1968:
            continue
        seen.add(title)
        films.append({"title": title, "rating": m.group(1), "year": year})
        if len(films) >= limit:
            break
    return films


def fetch_article_text(title: str) -> str:
    """Full plaintext of one article via the official API, disk-cached forever."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / (re.sub(r"[^A-Za-z0-9_-]", "_", title)[:120] + ".txt")
    if key.exists():
        return key.read_text()
    data = _get(
        WIKI_API,
        {
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "format": "json",
            "redirects": 1,
            "titles": title,
        },
    )
    pages = data.get("query", {}).get("pages", {})
    text = next(iter(pages.values()), {}).get("extract", "") or ""
    key.write_text(text)
    time.sleep(0.12)  # polite pacing; the cache makes reruns free
    return text


def extract_rationale(text: str, expected_rating: str) -> str | None:
    for rx in _PATTERNS:
        for m in rx.finditer(text):
            if m.group(1).upper() != expected_rating:
                continue  # QA: prose rating must corroborate Wikidata's
            rationale = m.group(2).strip().rstrip(",;: ")
            # Reject captures that are clearly not CARA descriptors.
            if re.search(r"\b(box office|weekend|dvd|blu-ray|premiere)\b", rationale, re.I):
                continue
            return rationale
    return None


def pilot(limit: int) -> int:
    films = fetch_film_list(limit)
    print(f"Wikidata returned {len(films)} rated films (top by sitelinks)\n")
    hits, misses, mismatches = [], [], 0
    for i, film in enumerate(films, 1):
        text = fetch_article_text(film["title"])
        rationale = extract_rationale(text, film["rating"])
        if rationale:
            hits.append({**film, "rationale": rationale})
        else:
            # Did the prose state a DIFFERENT rating? (regex hit, QA rejected)
            if any(rx.search(text) for rx in _PATTERNS):
                mismatches += 1
            misses.append(film["title"])
        if i % 25 == 0:
            print(f"  ...{i}/{len(films)} articles, {len(hits)} rationales so far")

    rate = len(hits) / max(1, len(films))
    print("\n=== PILOT RESULT ===")
    print(f"films: {len(films)}   rationales extracted: {len(hits)}   hit rate: {rate:.0%}")
    print(f"regex-hit-but-rating-mismatch (QA-dropped): {mismatches}")
    by_rating: dict[str, int] = {}
    for h in hits:
        by_rating[h["rating"]] = by_rating.get(h["rating"], 0) + 1
    print("by rating:", dict(sorted(by_rating.items())))
    print("\nsamples:")
    for h in hits[:10]:
        print(f"  {h['title']} ({h['year']}) — {h['rating']} for {h['rationale'][:90]}")
    out = CACHE / "pilot_result.json"
    out.write_text(json.dumps(hits, indent=2))
    print(f"\nfull result: {out}")
    return 0


# --- content-profile corpus -------------------------------------------------

TABLE = "rating_rationales"  # name predates the pivot; query_precedent selects from it
EMBED_MODEL = "text-embedding-005"
CORPUS = CACHE / "corpus.jsonl"


def _sections(text: str) -> tuple[str, str]:
    """(lead, plot) from a plaintext extract with == Section == headers."""
    parts = re.split(r"\n==+ *(.*?) *==+\n", text)
    lead = parts[0].strip()
    plot = ""
    for i in range(1, len(parts) - 1, 2):
        if re.fullmatch(r"plot|synopsis|premise|plot summary", parts[i].strip(), re.I):
            plot = parts[i + 1].strip()
            break
    return lead, plot


def _display_quote(lead: str) -> str:
    """First sentence(s) of the lead, cut at a sentence boundary, <= 220 chars."""
    quote = ""
    for m in re.finditer(r"[^.!?]+[.!?]", lead):
        if len(quote) + len(m.group(0)) > 220:
            break
        quote += m.group(0)
    return (quote or lead[:220]).strip()


def fetch(limit: int) -> int:
    films = fetch_film_list(limit)
    print(f"Wikidata: {len(films)} rated films (1968+, top by sitelinks)")
    rows, skipped = [], 0
    for i, film in enumerate(films, 1):
        text = fetch_article_text(film["title"])
        lead, plot = _sections(text)
        profile = (lead[:1200] + "\n" + plot[:2200]).strip()
        if len(profile) < 300:  # stub article: useless as a content profile
            skipped += 1
            continue
        title = re.sub(r" \((?:\d{4} )?film\)$", "", film["title"])
        rows.append(
            {
                "title": title,
                "year": film["year"],
                "rating": film["rating"],
                "quote": _display_quote(lead),
                "profile": profile,
                "source_url": "https://en.wikipedia.org/wiki/"
                + urllib.parse.quote(film["title"].replace(" ", "_")),
            }
        )
        if i % 100 == 0:
            print(f"  ...{i}/{len(films)} articles, {len(rows)} usable")
    CORPUS.write_text("\n".join(json.dumps(r) for r in rows))
    print(f"\nfetched {len(rows)} content profiles ({skipped} stubs skipped) -> {CORPUS}")
    return 0


def _vertex_client():
    import os

    from dotenv import load_dotenv
    from google import genai

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    return genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )


def _clickhouse():
    import os

    import clickhouse_connect
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    return clickhouse_connect.get_client(
        host=os.environ["CLICKHOUSE_HOST"],
        port=int(os.getenv("CLICKHOUSE_PORT", "8443")),
        username=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.environ["CLICKHOUSE_PASSWORD"],
        secure=True,
    )


def load() -> int:
    rows = [json.loads(line) for line in CORPUS.read_text().splitlines() if line]
    print(f"embedding {len(rows)} content profiles with {EMBED_MODEL}...")
    client = _vertex_client()
    for start in range(0, len(rows), 20):  # request cap: 20k tokens total
        batch = rows[start : start + 20]
        res = client.models.embed_content(model=EMBED_MODEL, contents=[r["profile"] for r in batch])
        for r, emb in zip(batch, res.embeddings, strict=True):
            r["embedding"] = list(emb.values)
        print(f"  ...{min(start + 20, len(rows))}/{len(rows)}") if (start // 20) % 10 == 0 else None
        time.sleep(0.15)

    ch = _clickhouse()
    ch.command(f"DROP TABLE IF EXISTS {TABLE}")
    ch.command(
        f"""
        CREATE TABLE {TABLE} (
          title String,
          year Int16,
          rating LowCardinality(String),
          rationale String,
          source_url String,
          embedding Array(Float32)
        ) ENGINE = MergeTree ORDER BY (rating, title)
        """
    )
    ch.insert(
        TABLE,
        [
            [r["title"], r["year"], r["rating"], r["quote"], r["source_url"], r["embedding"]]
            for r in rows
        ],
        column_names=["title", "year", "rating", "rationale", "source_url", "embedding"],
    )
    n = ch.query(f"SELECT count(), uniq(rating) FROM {TABLE}").result_rows[0]
    print(f"loaded: {n[0]} rows, {n[1]} distinct ratings")
    return 0


def query_smoke(text: str) -> int:
    client = _vertex_client()
    vec = list(client.models.embed_content(model=EMBED_MODEL, contents=text).embeddings[0].values)
    rows = (
        _clickhouse()
        .query(
            f"""SELECT title, year, rating, rationale,
                   cosineDistance(embedding, %(v)s) AS d
            FROM {TABLE} ORDER BY d ASC LIMIT 8""",
            parameters={"v": vec},
        )
        .result_rows
    )
    for title, year, rating, quote, d in rows:
        print(f"  {d:.3f}  {rating:<5} {title} ({year}) — {quote[:70]}")
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 200
    if arg == "pilot":
        sys.exit(pilot(n))
    if arg == "fetch":
        sys.exit(fetch(n if n != 200 else 2500))
    if arg == "load":
        sys.exit(load())
    if arg == "query":
        sys.exit(query_smoke(sys.argv[2]))
    print(__doc__)
    sys.exit(2)

#!/usr/bin/env python3
"""Rationale-space corpus: embed the OFFICIAL CARA rationale strings.

The main `rating_rationales` table deliberately embeds Wikipedia content
profiles (lead + plot) — the documented 2026-08 pivot, because rationale
strings are absent from Wikipedia prose. That corpus answers "which films are
ABOUT similar things?" — good enough for a rich desk rationale, badly wrong
for the What-If simulator: a post-cut profile like "for some strong language"
textually neighbors films whose PLOTS are about swearing (Swearnet, I Swear),
not films RATED for some strong language.

We hold the authoritative fix in .cache/ratings_ingest/rationales.jsonl: the
official filmratings.com rationale for 4,5xx corpus films. This script embeds
those strings into `cara_rationales`, so a CARA-phrased query is searched
against CARA-phrased documents — same language, honest neighbors. The rating
stored per row is the one INSIDE the official rationale string (a film
re-rated on appeal keeps its rationale's own rating, never Wikidata's).

    python scripts/ingest_cara_corpus.py load        # embed + create + insert
    python scripts/ingest_cara_corpus.py query "..."  # smoke-test kNN
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / ".cache" / "ratings_ingest" / "rationales.jsonl"
TABLE = "cara_rationales"
EMBED_MODEL = "text-embedding-005"  # must match toolbelt._embed

# Same shape rating_table.py parses the boundary from — one prefix rule.
_PREFIX = re.compile(r"^Rated\s+(G|PG-13|PG|R|NC-17)\s+for\s+", re.I)


def _vertex_client():
    import os

    from google import genai

    return genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("EMBED_LOCATION", "us-central1"),
    )


def _clickhouse():
    import os

    import clickhouse_connect

    return clickhouse_connect.get_client(
        host=os.environ["CLICKHOUSE_HOST"],
        username=os.environ.get("CLICKHOUSE_USER", "default"),
        password=os.environ["CLICKHOUSE_PASSWORD"],
        secure=True,
    )


def _rows() -> list[dict]:
    rows, seen = [], set()
    for line in SRC.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        text = (r.get("rationale") or "").strip()
        m = _PREFIX.match(text)
        if not m:
            continue
        key = (r["title"], r.get("year"))
        if key in seen:
            continue
        seen.add(key)
        clause = "for " + text[m.end() :].strip()[:300]
        rows.append(
            {
                "title": r["title"],
                "year": int(r.get("year") or 0),
                # the rating token inside the official string, not Wikidata's
                "rating": m.group(1).upper(),
                "rationale": text[:400],
                "embed_text": clause,
                "source_url": "https://www.filmratings.com/Search?filmTitle="
                + urllib.parse.quote(r.get("fr_title") or r["title"]),
            }
        )
    return rows


def load() -> int:
    rows = _rows()
    print(f"official rationales parsed: {len(rows)} (of {sum(1 for _ in SRC.open())} films)")
    client = _vertex_client()
    for start in range(0, len(rows), 20):
        batch = rows[start : start + 20]
        res = client.models.embed_content(
            model=EMBED_MODEL, contents=[r["embed_text"] for r in batch]
        )
        for r, emb in zip(batch, res.embeddings, strict=True):
            r["embedding"] = list(emb.values)
        if (start // 20) % 20 == 0:
            print(f"  ...{min(start + 20, len(rows))}/{len(rows)}")
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
            [r["title"], r["year"], r["rating"], r["rationale"], r["source_url"], r["embedding"]]
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
        print(f"  {d:.3f}  {rating:<5} {title} ({year}) — {quote[:80]}")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "load"
    if cmd == "load":
        raise SystemExit(load())
    if cmd == "query":
        raise SystemExit(query_smoke(sys.argv[2]))
    print(__doc__)
    raise SystemExit(2)

"""What-if rating projection: re-run the evidence pipeline with beats cut.

The report's cut list says "remove these beats to reach your target rating."
This module makes that claim testable: given a subset of cuts, it rewrites the
content rationale minus the cut material (Gemini Flash, temperature 0 — the
only model step), re-embeds it with the same model the corpus was built with,
re-queries the ClickHouse comparables, and re-tallies. Same pipeline, new
evidence — never a model asserting "that would probably be PG-13."
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from greenlight import storage
from greenlight.tools import toolbelt

_REWRITE_PROMPT = """You are revising an MPA/CARA-style content rationale after script cuts.

ORIGINAL RATIONALE (describes the script as written):
{rationale}

CUTS BEING MADE:
{cuts}

Write the revised rationale describing ONLY the content that remains after these
cuts. Same terse CARA phrasing ("for strong language, brief violence..."). Do not
invent content that was not in the original rationale. Do not mention the cuts or
ratings. If a content category is only reduced (not eliminated), soften its
wording (e.g. "multiple uses" -> "a use"). 1-2 sentences, output the rationale
text only."""


def _revise_rationale(rationale: str, cuts: list[str]) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )
    res = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=_REWRITE_PROMPT.format(
            rationale=rationale, cuts="\n".join(f"- {c}" for c in cuts)
        ),
        config=types.GenerateContentConfig(temperature=0.0),
    )
    return (res.text or "").strip() or rationale


def project(record: dict[str, Any], run_id: str, cut_indices: list[int]) -> dict[str, Any]:
    """Projected rating for `record` with the given beats_to_cut indices applied."""
    pred = (record.get("report") or {}).get("rating_prediction") or {}
    beats = pred.get("beats_to_cut") or []
    rationale = pred.get("rationale") or ""
    if not beats or not rationale:
        return {"error": "This run has no cut list to simulate."}
    cuts = [beats[i] for i in sorted(set(cut_indices)) if 0 <= i < len(beats)]
    if not cuts:
        return {"error": "No cuts selected."}

    mask = ",".join(str(i) for i in sorted(set(cut_indices)))
    key = "whatif:" + hashlib.sha256(f"{run_id}|{mask}|{rationale}".encode()).hexdigest()[:24]
    if (cached := storage.load_research(key)) is not None:
        return cached

    revised = _revise_rationale(rationale, cuts)
    vec = toolbelt._embed(revised)
    rows = (
        toolbelt._clickhouse_client()
        .query(
            """
        SELECT title, year, rating, source_url,
               cosineDistance(embedding, %(vec)s) AS distance
        FROM rating_rationales
        ORDER BY distance ASC
        LIMIT 8
        """,
            parameters={"vec": vec},
        )
        .result_rows
    )
    comparables = [
        {
            "title": r[0],
            "year": r[1],
            "rating": r[2],
            "source_url": r[3],
            "distance": round(float(r[4]), 4),
        }
        for r in rows
    ]
    tally: dict[str, int] = {}
    for c in comparables:
        tally[c["rating"]] = tally.get(c["rating"], 0) + 1
    projected = max(tally.items(), key=lambda kv: kv[1])[0] if tally else "?"
    result = {
        "projected": projected,
        "tally": tally,
        "revised_rationale": revised,
        "comparables": comparables,
        "cuts_applied": len(cuts),
    }
    storage.save_research(key, result)
    return result

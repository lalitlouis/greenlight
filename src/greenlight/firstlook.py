"""First Look, wave 2: one fast Flash call while the desks warm up.

Logline, genre/tone, three craft observations, and a capsule content profile
that drives a comparables lookup against the corpus. These are 40-second
FIRST IMPRESSIONS — explicitly unverified, rendered under that label, and
never dressed as findings. The desks' cited, verified work is the product;
this card is company for the wait.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel

from greenlight import runstate

_PROMPT = """You are giving a fast first read of a screenplay — the impressions a
seasoned reader forms in the first pass, before any research.

Return:
- logline: one sentence, the story as it actually is on the page (not a pitch).
- genre: 2-4 words ("dark comedy", "grounded thriller").
- tone: 3-6 words.
- observations: exactly 3 short craft observations a professional reader would
  make — specific to THIS script, plainspoken, one sentence each. Honest but
  not cruel; no scores, no verdicts.
- content_capsule: 1-2 sentences describing the rating-relevant content in
  CARA rationale style (for a similarity search; not shown to the user).

SCREENPLAY (may be truncated):
{script}
"""

_MAX_SCRIPT_CHARS = 120_000  # ~30k tokens — plenty for a first impression


class FirstLook(BaseModel):
    logline: str
    genre: str
    tone: str
    observations: list[str]
    content_capsule: str


def _comps(capsule: str) -> list[dict[str, Any]]:
    from greenlight.tools import toolbelt

    try:
        vec = toolbelt._embed(capsule)
        rows = (
            toolbelt._clickhouse_client()
            .query(
                """
            SELECT title, year, rating, cosineDistance(embedding, %(vec)s) AS d
            FROM rating_rationales ORDER BY d ASC LIMIT 5
            """,
                parameters={"vec": vec},
            )
            .result_rows
        )
        return [{"title": r[0], "year": r[1], "rating": r[2]} for r in rows]
    except Exception:
        return []


def run_first_look(run_id: str, source: str) -> dict[str, Any] | None:
    """Compute and persist the first-look card. Synchronous — callers thread it.
    Failure is silent by design: this card is garnish, never a run blocker."""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
        res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=_PROMPT.format(script=source[:_MAX_SCRIPT_CHARS]),
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=FirstLook,
            ),
        )
        look = FirstLook.model_validate_json(res.text)
        data = {
            "logline": look.logline,
            "genre": look.genre,
            "tone": look.tone,
            "observations": look.observations[:3],
            "comps": _comps(look.content_capsule),
        }
        runstate.run_set(run_id, {"first_look": data})
        return data
    except Exception:
        return None

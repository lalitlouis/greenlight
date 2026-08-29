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
from typing import Any

from greenlight import storage
from greenlight.models import FLASH_MODEL
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


_EMBED_MEMO: dict[str, list[float]] = {}
_EMBED_MEMO_MAX = 512


def _embed_cached(text: str) -> list[float]:
    """Rationale embeddings are pure functions of their text — repeated What-If
    cuts (users toggle the same boxes) must not re-bill the pinned us-central1
    embed quota. In-process memo first, then the GCS research-cache namespace."""
    import hashlib

    from greenlight import storage
    from greenlight.tools import toolbelt

    key = "embed-" + hashlib.sha1(text.encode()).hexdigest()[:16]
    if key in _EMBED_MEMO:
        return _EMBED_MEMO[key]
    stored = storage.load_research(key)
    if stored and isinstance(stored.get("vec"), list):
        vec = stored["vec"]
    else:
        vec = toolbelt._embed(text)
        storage.save_research(key, {"vec": vec})
    if len(_EMBED_MEMO) >= _EMBED_MEMO_MAX:
        _EMBED_MEMO.pop(next(iter(_EMBED_MEMO)))
    _EMBED_MEMO[key] = vec
    return vec


def _revise_rationale(rationale: str, cuts: list[str]) -> str:
    from google.genai import types

    from greenlight.llmclient import vertex_client

    client = vertex_client()
    res = client.models.generate_content(
        model=FLASH_MODEL,
        contents=_REWRITE_PROMPT.format(
            rationale=rationale, cuts="\n".join(f"- {c}" for c in cuts)
        ),
        config=types.GenerateContentConfig(temperature=0.0),
    )
    return (res.text or "").strip() or rationale


def project(
    record: dict[str, Any],
    run_id: str,
    cut_indices: list[int],
    extra_cuts: list[str] | None = None,
) -> dict[str, Any]:
    """Projected rating for `record` with the given beats_to_cut indices applied,
    plus any simulator-suggested extra cuts the user opted into."""
    pred = (record.get("report") or {}).get("rating_prediction") or {}
    beats = pred.get("beats_to_cut") or []
    rationale = pred.get("rationale") or ""
    if not beats or not rationale:
        return {"error": "This run has no cut list to simulate."}
    extras = [e.strip()[:220] for e in (extra_cuts or []) if e.strip()][:4]
    cuts = [beats[i] for i in sorted(set(cut_indices)) if 0 <= i < len(beats)] + extras
    if not cuts:
        return {"error": "No cuts selected."}

    mask = ",".join(str(i) for i in sorted(set(cut_indices))) + "|" + "|".join(extras)
    key = "whatif:" + hashlib.sha256(f"{run_id}|{mask}|{rationale}".encode()).hexdigest()[:24]
    if (cached := storage.load_research(key)) is not None:
        return cached

    revised = _revise_rationale(rationale, cuts)
    vec = _embed_cached(revised)
    rows = (
        toolbelt._clickhouse_client()
        .query(
            """
        SELECT title, year, rating, source_url,
               cosineDistance(embedding, %(vec)s) AS distance
        FROM rating_rationales
        WHERE lower(title) != lower(%(skip_title)s)
        ORDER BY distance ASC
        LIMIT 8
        """,
            parameters={
                "vec": vec,
                # the film itself must not vote in its own What-If — the live
                # prediction excludes self-matches (query_precedent); this
                # query never inherited that until now
                "skip_title": str(record.get("script_title") or ""),
            },
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
    # ONE voting rule, shared with the live prediction — plain plurality here
    # once let the same neighbours answer differently in two report panels
    projected = toolbelt.comps_weighted_majority(comparables) or "?"
    result = {
        "projected": projected,
        "tally": tally,
        "revised_rationale": revised,
        "comparables": comparables,
        "cuts_applied": len(cuts),
    }
    storage.save_research(key, result)
    return result


_SUGGEST_PROMPT = """A screenplay's content profile is being edited toward a target MPA rating.

CURRENT (revised) CONTENT PROFILE:
{revised}

TARGET RATING: {target}
Of its 8 nearest released comparables, {n_higher} still rate {projected}.

ALREADY-PLANNED CUTS (do not repeat these):
{cuts}

Identify which elements of the current profile most separate it from typical {target}
films, then propose up to 3 additional, concrete, minimal script-level adjustments
that address exactly those elements. Rules:
- Each suggestion is one imperative line a screenwriter could act on
  (e.g. "Move the drinking off-screen: characters reference it, we never see impairment").
- Prefer softening/reframing over deleting whole subject matter; themes like grief
  are {target}-compatible and should not be cut.
- Never invent scene numbers or content not implied by the profile.
Output one suggestion per line, no numbering, no commentary."""


def suggest(
    record: dict[str, Any],
    run_id: str,
    cut_indices: list[int],
    extra_cuts: list[str] | None = None,
) -> dict[str, Any]:
    """Additional levers toward the target — grounded in the revised profile the
    simulator just tested, each returned as a testable cut candidate."""
    pred = (record.get("report") or {}).get("rating_prediction") or {}
    target = pred.get("target") or ""
    if not target:
        return {"error": "This run has no target rating."}
    base = project(record, run_id, cut_indices, extra_cuts)
    if "error" in base:
        return base
    revised = base["revised_rationale"]
    key = "whatifsug:" + hashlib.sha256(f"{run_id}|{revised}|{target}".encode()).hexdigest()[:24]
    if (cached := storage.load_research(key)) is not None:
        return cached

    beats = pred.get("beats_to_cut") or []
    planned = [beats[i] for i in sorted(set(cut_indices)) if 0 <= i < len(beats)] + list(
        extra_cuts or []
    )
    n_higher = base["tally"].get(base["projected"], 0)

    from google.genai import types

    from greenlight.llmclient import vertex_client

    client = vertex_client()
    res = client.models.generate_content(
        model=FLASH_MODEL,
        contents=_SUGGEST_PROMPT.format(
            revised=revised,
            target=target,
            n_higher=n_higher,
            projected=base["projected"],
            cuts="\n".join(f"- {c}" for c in planned) or "- (none)",
        ),
        config=types.GenerateContentConfig(temperature=0.0),
    )
    min_chars = 15  # shorter lines are fragments, not actionable cuts
    lines = [ln.strip("-• ").strip() for ln in (res.text or "").splitlines()]
    suggestions = [ln for ln in lines if len(ln) > min_chars][:3]
    result = {"suggestions": suggestions, "based_on": revised}
    storage.save_research(key, result)
    return result

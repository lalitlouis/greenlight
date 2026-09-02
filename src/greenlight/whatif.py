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

# Below this, a rationale is too thin to embed meaningfully — kNN neighbors
# collapse onto the corpus outlier cluster and stop answering the question.
_SPARSE_RATIONALE_CHARS = 60


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


_FALLBACK_INTENSITIES = (
    "pervasive", "graphic", "strong bloody", "strong", "intense", "sustained", "crude",
    "brief", "mild", "some", "partial", "brutal", "grisly", "explicit", "bloody",
)  # fmt: skip


def _intensities() -> tuple[str, ...]:
    """The harvest vocabulary's intensity words (embedded in the boundary asset)
    so the splitter re-binds exactly what the corpus parser re-binds."""
    try:
        vocab = (toolbelt._boundary_data().get("vocabulary") or {}).get("intensities") or []
        words = tuple(str(w).lower() for w in vocab)
        return tuple(dict.fromkeys([*words, "bloody"]))
    except Exception:
        return _FALLBACK_INTENSITIES


def _descriptor_phrases(rationale: str) -> list[str]:
    """Split a CARA-style rationale into descriptor phrases for boundary_eval.
    "Rated R for pervasive language, some violence and brief nudity." ->
    ["pervasive language", "some violence", "brief nudity"]. A bare intensity
    fragment re-binds to what follows it ("strong, bloody violence" -> "strong
    bloody violence"), mirroring the harvest parser — otherwise the boundary
    reports an unmatched "strong" and the simulator falls back to kNN on exactly
    the heavy-violence profiles."""
    import re

    t = rationale.strip().strip("\u201c\u201d\"' ")
    t = re.sub(r"^\s*(rated\s+[\w-]+\s+)?for\s+", "", t, flags=re.I)
    t = t.rstrip(". ").strip("\u201c\u201d\"' ")
    parts: list[str] = []
    intensities = _intensities()
    for chunk in re.split(r",|;", t):
        for raw in re.split(r"\s+and\s+", chunk):
            piece = raw.strip().strip("\u201c\u201d\"' ")
            if not piece:
                continue
            if parts and parts[-1].lower() in intensities:
                parts[-1] = f"{parts[-1]} {piece}"[:80]
            else:
                parts.append(piece[:80])
    return parts[:8]


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
    key = "whatif:v3:" + hashlib.sha256(f"{run_id}|{mask}|{rationale}".encode()).hexdigest()[:24]
    if (cached := storage.load_research(key)) is not None:
        return cached

    try:
        revised = _revise_rationale(rationale, cuts)
    except Exception as exc:  # the only model step; a 500 here was a blank toast
        return {
            "error": "The profile rewrite is unavailable right now — try again shortly.",
            "unavailable": True,
            "detail": type(exc).__name__,
        }

    # The measured boundary is the primary instrument for a post-cut profile.
    # kNN re-embeds the revised rationale text, and a sparse rationale ("for
    # brief strong language") collapses onto the corpus's outlier cluster —
    # films rated R/NC-17 *solely* for language — answering "whose rationale
    # text looks like this?" instead of "what does this profile rate?" (the
    # Swearnet-neighbors run, 2026-09-01). When every descriptor matches the
    # vocabulary and the conformal set is a single rating, that measured
    # answer IS the projection; neighbors become secondary color.
    phrases = _descriptor_phrases(revised)
    boundary: dict[str, Any] = {}
    try:
        b = toolbelt.boundary_eval(phrases)
        boundary = {
            "matched": b["matched"],
            "unmatched": b["unmatched"],
            "prediction_set": b["prediction_set"],
            "probabilities": b["probabilities"],
            # specific (intensity+category) marginals first — smaller n
            "marginals": sorted(b["marginals"].values(), key=lambda m: m["n"]),
        }
    except Exception:
        boundary = {}
    neighbors_sparse = len(phrases) <= 1 or len(revised) < _SPARSE_RATIONALE_CHARS

    # v3: neighbors come from cara_rationales — OFFICIAL filmratings.com
    # rationale strings embedded in rationale-space (scripts/ingest_cara_corpus).
    # The content-profile table matched plots ("films ABOUT swearing"), which
    # is what put Swearnet atop a one-F-word profile.
    comparables, neighbors_error = _neighbors(revised, str(record.get("script_title") or ""))
    tally: dict[str, int] = {}
    for c in comparables:
        tally[c["rating"]] = tally.get(c["rating"], 0) + 1
    # ONE voting rule, shared with the live prediction — plain plurality here
    # once let the same neighbours answer differently in two report panels
    neighbors_vote = toolbelt.comps_weighted_majority(comparables) or "?"
    b_set = boundary.get("prediction_set") or []
    boundary_answers = bool(
        b_set and len(b_set) == 1 and boundary.get("matched") and not boundary.get("unmatched")
    )
    if boundary_answers:
        projected, basis = b_set[0], "boundary"
    elif comparables:
        projected, basis = neighbors_vote, "neighbors"
    else:
        # neither instrument can answer: say so, never a 500 and never a guess
        return {
            "error": "Comparables are unavailable right now and the measured boundary does "
            "not narrow this profile to one rating — try again shortly.",
            "unavailable": True,
            "detail": neighbors_error,
            "boundary": boundary,
            "revised_rationale": revised,
        }
    if boundary_answers and boundary.get("marginals"):
        boundary["driver"] = _driver_marginal(boundary["marginals"], projected)
    result = {
        "projected": projected,
        "basis": basis,
        "neighbors_vote": neighbors_vote,
        "boundary": boundary,
        "neighbors_sparse": neighbors_sparse,
        "neighbors_unavailable": bool(neighbors_error),
        "tally": tally,
        "revised_rationale": revised,
        "comparables": comparables,
        "cuts_applied": len(cuts),
    }
    if not neighbors_error:
        storage.save_research(key, result)  # a degraded answer is never cached
    return result


def _neighbors(revised: str, skip_title: str) -> tuple[list[dict[str, Any]], str]:
    """The eight nearest official rationales, or ([], why-not). The embed and
    the ClickHouse query are live dependencies; a blip must degrade to
    "comparables unavailable", not surface as a 500 (review C11)."""
    try:
        vec = _embed_cached(revised)
        rows = (
            toolbelt._clickhouse_client()
            .query(
                """
            SELECT title, year, rating, source_url, rationale,
                   cosineDistance(embedding, %(vec)s) AS distance
            FROM cara_rationales
            WHERE lower(title) != lower(%(skip_title)s)
            ORDER BY distance ASC, year DESC
            LIMIT 8
            """,
                parameters={
                    "vec": vec,
                    # the film itself must not vote in its own What-If — the live
                    # prediction excludes self-matches (query_precedent)
                    "skip_title": skip_title,
                },
            )
            .result_rows
        )
    except Exception as exc:
        return [], type(exc).__name__
    return [
        {
            "title": r[0],
            "year": r[1],
            "rating": r[2],
            "source_url": r[3],
            # the film's own official rationale — the chip can show WHY it voted
            "rationale": r[4],
            "distance": round(float(r[5]), 4),
        }
        for r in rows
    ], ""


def _driver_marginal(marginals: list[dict[str, Any]], projected: str) -> dict[str, Any] | None:
    """The descriptor that most drives the projected rating: among matched
    marginals, the one whose share for `projected` is highest (ties -> smaller
    n, i.e. more specific). The renderer's old rule — marginals[0], the smallest
    n overall — could quote a descriptor that argues AGAINST the projection."""

    def share(m: dict[str, Any]) -> float:
        raw = str((m.get("distribution") or {}).get(projected, "0")).rstrip("%")
        try:
            return float(raw)
        except ValueError:
            return 0.0

    ranked = sorted(marginals, key=lambda m: (-share(m), m.get("n", 0)))
    return dict(ranked[0]) if ranked else None


_SUGGEST_PROMPT = """A screenplay's content profile is being edited toward a target MPA rating.

CURRENT (revised) CONTENT PROFILE:
{revised}

TARGET RATING: {target}
{evidence}

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
    evidence = suggest_evidence(base)

    from google.genai import types

    from greenlight.llmclient import vertex_client

    client = vertex_client()
    res = client.models.generate_content(
        model=FLASH_MODEL,
        contents=_SUGGEST_PROMPT.format(
            revised=revised,
            target=target,
            evidence=evidence,
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


def suggest_evidence(base: dict[str, Any]) -> str:
    """The one evidence sentence the suggestion prompt reasons from. When the
    measured boundary carried the projection, the neighbours are NOT the
    evidence and must not be cited as if they were (the Swearnet class);
    quote the driving marginal instead."""
    projected = base.get("projected") or "?"
    if base.get("basis") == "boundary":
        drv = (base.get("boundary") or {}).get("driver") or {}
        pct = (drv.get("distribution") or {}).get(projected)
        if drv.get("descriptor") and pct:
            return (
                f"On the measured CARA boundary the revised profile still reads {projected}: "
                f"'{drv['descriptor']}' draws {projected} in {pct} of {drv.get('n', '?')} "
                "official rationales."
            )
        return f"On the measured CARA boundary the revised profile still reads {projected}."
    n_higher = (base.get("tally") or {}).get(projected, 0)
    return f"Of its 8 nearest released comparables, {n_higher} still rate {projected}."

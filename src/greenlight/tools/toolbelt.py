"""The desk toolbelt. Every gatekeeper gets these; desks differ only in instruction.

Docstrings are written for the model — ADK sends the signature and docstring as the
tool spec. Keep them imperative and concrete.

Design rules (see docs/TECH_SPEC.md):
- The citation invariant lives HERE, at the file_flag boundary, not in a prompt.
- research() is the only tool that spends money. It is budgeted and cached.
- done() is how a LoopAgent desk ends itself: it sets escalate.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any
from urllib.parse import urlparse

from google.adk.tools import ToolContext

from greenlight.contracts import ContractViolation, validate

DESKS = ("clearance_counsel", "ratings_board", "safety_underwriter", "territory_censor")

# The four desks run concurrently under a ParallelAgent. Shared counters would race,
# so flag ids are partitioned per desk and research budgets are per-desk keys.
FLAG_ID_OFFSET = {
    "clearance_counsel": 100,
    "ratings_board": 200,
    "safety_underwriter": 300,
    "territory_censor": 400,
}

_MAX_RESULTS_TO_MODEL = 6
_MAX_EXCERPT_CHARS = 1200


def _desk(tool_context: ToolContext) -> str:
    name = tool_context.agent_name
    for desk in DESKS:
        if name.startswith(desk):
            return desk
    raise RuntimeError(f"tool called from unknown desk agent {name!r}")


def _state_append(tool_context: ToolContext, key: str, item: Any) -> None:
    items = list(tool_context.state.get(key, []))
    items.append(item)
    tool_context.state[key] = items


# --- read_scene -------------------------------------------------------------


def read_scene(scene_id: str, tool_context: ToolContext) -> str:
    """Read the full text of one scene, exactly as written in the screenplay.

    Use this to see context around an entity before researching it: who is present,
    how prominent something is, whether it is depicted negatively. scene_id is the
    id shown in your worklist, e.g. "S004".
    """
    for scene in tool_context.state.get("scenes", []):
        if scene["scene_id"] == scene_id:
            start, end = scene["raw_span"]
            return tool_context.state["script_text"][start:end]
    known = ", ".join(s["scene_id"] for s in tool_context.state.get("scenes", []))
    return f"No scene {scene_id!r}. Valid scene ids: {known}"


# --- find_in_script ---------------------------------------------------------


def find_in_script(pattern: str, tool_context: ToolContext) -> dict[str, Any]:
    """Find where and how often a word or phrase appears across the whole screenplay.

    Prominence is a fact, not a guess — use this to establish it. pattern is a
    case-insensitive regular expression; plain words work fine. Returns per-scene
    match counts and the matching lines.
    """
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return {"error": f"bad pattern: {e}"}
    hits: list[dict[str, Any]] = []
    total = 0
    text = tool_context.state["script_text"]
    for scene in tool_context.state.get("scenes", []):
        start, end = scene["raw_span"]
        chunk = text[start:end]
        lines = [ln.strip() for ln in chunk.split("\n") if rx.search(ln)]
        if lines:
            n = sum(len(rx.findall(ln)) for ln in lines)
            total += n
            hits.append({"scene_id": scene["scene_id"], "count": n, "lines": lines[:5]})
    return {"pattern": pattern, "total_matches": total, "scenes": hits}


# --- research ---------------------------------------------------------------


def _live_search(objective: str, queries: list[str]) -> dict[str, Any]:
    """The live Parallel Search call. Module-level so tests can monkeypatch it.

    This call is the partner-track requirement — it must stay on the default path.
    """
    import parallel

    client = parallel.Parallel(api_key=os.environ["PARALLEL_API_KEY"])
    res = client.search(
        search_queries=queries,
        objective=objective,
        mode="advanced",
        max_chars_total=8000,
    )
    return res.model_dump()


def _normalize_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.netloc.lower()}{p.path.rstrip('/').lower()}"


def _compact(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Dedup on normalized URL (Parallel returns case-variant duplicates) and trim."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in raw.get("results", []):
        key = _normalize_url(r["url"])
        if key in seen:
            continue
        seen.add(key)
        excerpts, used = [], 0
        for ex in r.get("excerpts", []):
            if used >= _MAX_EXCERPT_CHARS:
                break
            excerpts.append(ex[: _MAX_EXCERPT_CHARS - used])
            used += len(ex)
        out.append(
            {
                "url": r["url"],
                "title": r.get("title"),
                "publish_date": r.get("publish_date"),
                "excerpts": excerpts,
            }
        )
        if len(out) >= _MAX_RESULTS_TO_MODEL:
            break
    return out


def research(
    objective: str, queries: list[str], entity_id: str, tool_context: ToolContext
) -> dict[str, Any]:
    """Research a clearance question on the live web. Returns sourced, verbatim excerpts.

    objective: the actual clearance question, in full prose, self-contained — include
    the entity's script context (who, where, how depicted). This drives result quality.
    queries: 2-3 short keyword retrieval strings, 3-6 words each. Not sentences.
    entity_id: the worklist entity this research is for, e.g. "E003". Pass "" if the
    question is not about a single entity.

    Results are shared across desks — researching an already-researched entity is free.
    Every citation you file must copy an excerpt from these results VERBATIM. Never
    paraphrase an excerpt.
    """
    # Key on entity AND question: an ownership chase asks several different
    # questions about one entity, and each deserves its own search. Identical
    # questions still share across desks.
    q_hash = hashlib.sha1(objective.encode()).hexdigest()[:12]
    key = f"research:{entity_id}:{q_hash}" if entity_id else f"research:{q_hash}"
    cached = tool_context.state.get(key)
    if cached is not None:
        return {"cached": True, "results": cached["results"], "search_id": cached["search_id"]}

    budget_key = f"research_budget:{_desk(tool_context)}"
    budget = int(tool_context.state.get(budget_key, 0))
    if budget <= 0:
        return {
            "error": "research budget spent",
            "guidance": (
                "File flags you can already support with earlier results, record what "
                "you could not resolve with note_open_question, then call done()."
            ),
        }

    raw = _live_search(objective, queries)
    tool_context.state[budget_key] = budget - 1
    compacted = _compact(raw)
    record = {
        "objective": objective,
        "search_id": raw.get("search_id", ""),
        "results": compacted,
    }
    tool_context.state[key] = record
    return {
        "cached": False,
        "budget_remaining": budget - 1,
        "search_id": record["search_id"],
        "results": compacted,
    }


# --- file_flag --------------------------------------------------------------


def file_flag(
    scene_ids: list[str],
    severity: str,
    category: str,
    finding: str,
    citations: list[dict],
    remedy_action: str,
    remedy_detail: str,
    confidence: float,
    tool_context: ToolContext,
    entity_id: str = "",
    est_cost_usd_low: float = -1,
    est_cost_usd_high: float = -1,
    est_added_days: float = -1,
) -> str:
    """File one finding. A flag without a citation is REJECTED — this is enforced.

    scene_ids: the scenes the finding anchors to, e.g. ["S004"].
    severity: BLOCKER | HIGH | MEDIUM | LOW | FYI. BLOCKER means cannot shoot or
      cannot release as written.
    category: short slug, e.g. "sync_license", "trademark_disparagement", "stunt_pyro".
    finding: one paragraph, plain English, addressed to a producer.
    citations: at least one. Each is an object with keys: source_type ("web"),
      title, url, excerpt, via ("parallel_search"). excerpt must be VERBATIM text
      copied from a research() result — never paraphrased, never invented.
    remedy_action: REPLACE | OBTAIN_LICENSE | OBTAIN_RELEASE | RESHOOT |
      ADD_DISCLAIMER | ADD_SPECIALIST | CUT | NO_ACTION.
    remedy_detail: concrete and actionable — "rename to a fictional brand", not
      "consider alternatives".
    confidence: 0.0-1.0, your confidence in the finding.
    entity_id: the entity this concerns, or "" for findings not tied to one.
    est_cost_usd_low/high: rule-of-thumb remedy cost range in USD; pass -1 if unknown.
    est_added_days: schedule impact in days; pass -1 if unknown.

    On rejection you get every validation error at once — fix them all and refile once.
    """
    desk = _desk(tool_context)
    seq_key = f"flag_seq:{desk}"
    seq = int(tool_context.state.get(seq_key, 0)) + 1
    tool_context.state[seq_key] = seq

    cits = []
    for c in citations:
        cit = {
            "source_type": c.get("source_type", "web"),
            "title": c.get("title", ""),
            "url": c.get("url"),
            "excerpt": c.get("excerpt", ""),
            "retrieved_at": None,
            "via": c.get("via", "parallel_search"),
        }
        cits.append(cit)

    flag: dict[str, Any] = {
        "flag_id": f"F{FLAG_ID_OFFSET[desk] + seq}",
        "agent": desk,
        "scene_ids": scene_ids,
        "entity_id": entity_id or None,
        "severity": severity,
        "category": category,
        "finding": finding,
        "citations": cits,
        "remedy": {
            "action": remedy_action,
            "detail": remedy_detail,
            "est_cost_usd": (
                [est_cost_usd_low, est_cost_usd_high]
                if est_cost_usd_low >= 0 and est_cost_usd_high >= 0
                else None
            ),
            "est_added_days": est_added_days if est_added_days >= 0 else None,
        },
        "confidence": confidence,
    }

    try:
        validate("flag", flag)
    except ContractViolation as e:
        tool_context.state[seq_key] = seq - 1
        return "REJECTED, not filed. Fix ALL of these and refile once:\n- " + "\n- ".join(e.errors)

    if not all(c["excerpt"].strip() for c in cits):
        tool_context.state[seq_key] = seq - 1
        return "REJECTED, not filed: every citation needs a non-empty verbatim excerpt."

    known = {s["scene_id"] for s in tool_context.state.get("scenes", [])}
    if bad := [s for s in scene_ids if s not in known]:
        tool_context.state[seq_key] = seq - 1
        return f"REJECTED, not filed: unknown scene ids {bad}. Use ids from your worklist."

    _state_append(tool_context, f"flags:{desk}", flag)
    return f"Filed {flag['flag_id']} ({severity} {category})."


# --- query_precedent --------------------------------------------------------


def _clickhouse_client():
    """Lazy ClickHouse client. Module-level so tests can monkeypatch it."""
    import clickhouse_connect

    return clickhouse_connect.get_client(
        host=os.environ["CLICKHOUSE_HOST"],
        port=int(os.getenv("CLICKHOUSE_PORT", "8443")),
        username=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.environ["CLICKHOUSE_PASSWORD"],
        secure=os.getenv("CLICKHOUSE_SECURE", "true").lower() == "true",
    )


def _embed(text: str) -> list[float]:
    """Embed text with Vertex — must match the model used at corpus ingest time."""
    from google import genai

    client = genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )
    res = client.models.embed_content(model="text-embedding-005", contents=text)
    return list(res.embeddings[0].values)


def query_precedent(text: str, k: int, tool_context: ToolContext) -> dict[str, Any]:
    """Find the k nearest released films by MPA/CARA rating rationale.

    text: a capsule content profile of THIS script — the rating-relevant facts in the
    style of a rating rationale, e.g. "strong language throughout, brief violence,
    drug use, thematic elements involving grief". 1-3 sentences.
    k: how many comparables, typically 8.

    Returns released films with their actual rating, official rationale, and distance
    (smaller = more similar). This is evidence — cite it with source_type "precedent"
    and via "clickhouse", quoting the rationale verbatim as the excerpt. If you get an
    error field back, the corpus is unavailable: fall back to research() on documented
    CARA standards instead.
    """
    if _missing_env := [v for v in ("CLICKHOUSE_HOST", "CLICKHOUSE_PASSWORD") if not os.getenv(v)]:
        return {
            "error": f"precedent corpus not configured ({', '.join(_missing_env)} unset)",
            "guidance": "Fall back to research() on documented CARA standards.",
        }
    try:
        vec = _embed(text)
        rows = (
            _clickhouse_client()
            .query(
                """
            SELECT title, year, rating, rationale, source_url,
                   cosineDistance(embedding, %(vec)s) AS distance
            FROM rating_rationales
            ORDER BY distance ASC
            LIMIT %(k)s
            """,
                parameters={"vec": vec, "k": max(1, min(int(k), 20))},
            )
            .result_rows
        )
    except Exception as e:
        return {
            "error": f"precedent corpus unavailable: {type(e).__name__}: {str(e)[:120]}",
            "guidance": "Fall back to research() on documented CARA standards.",
        }
    comparables = [
        {
            "title": r[0],
            "year": r[1],
            "rating": r[2],
            "rationale": r[3],
            "source_url": r[4],
            "distance": round(float(r[5]), 4),
        }
        for r in rows
    ]
    # The prediction tool assembles the report's rating_prediction from the most
    # recent comparables — stored here so the desk never re-types them.
    tool_context.state[f"last_precedent:{_desk(tool_context)}"] = comparables
    return {"comparables": comparables}


# --- file_rating_prediction -------------------------------------------------


def file_rating_prediction(
    predicted: str,
    rationale: str,
    beats_to_cut: list[str],
    tool_context: ToolContext,
) -> str:
    """File the MPA rating prediction for the report. Ratings Board only; call once,
    after query_precedent has returned comparables.

    predicted: the rating this screenplay draws as written: G | PG | PG-13 | R | NC-17.
    rationale: one sentence in CARA house style, e.g. "for strong language throughout,
      drug use and brief violence" — derived from your counted findings.
    beats_to_cut: if the production's target rating (in your instructions) is below
      `predicted`, the exact changes that buy the target, most impactful first, e.g.
      "Cut 2 of the 3 F-bombs; keep Danny's in S011". Empty list if already at target.

    The comparables from your most recent query_precedent call are attached
    automatically as the evidence. Filing without comparables is rejected.
    """
    desk = _desk(tool_context)
    comparables = tool_context.state.get(f"last_precedent:{desk}")
    if not comparables:
        return (
            "REJECTED: no comparables on record. Call query_precedent first — the "
            "prediction's evidence is the nearest released films, not your judgement."
        )
    if predicted not in {"G", "PG", "PG-13", "R", "NC-17"}:
        return "REJECTED: predicted must be one of G, PG, PG-13, R, NC-17."
    tool_context.state["rating_prediction"] = {
        "predicted": predicted,
        "target": tool_context.state.get("target_rating"),
        "rationale": rationale,
        "comparables": comparables,
        "beats_to_cut": list(beats_to_cut),
    }
    dist: dict[str, int] = {}
    for c in comparables:
        dist[c["rating"]] = dist.get(c["rating"], 0) + 1
    return f"Prediction filed: {predicted}. Comparable ratings: {dist}."


# --- note_open_question -----------------------------------------------------


def note_open_question(question: str, tool_context: ToolContext) -> str:
    """Record something you could not resolve. Surfaced in the report as an honest
    unknown — an honest unknown beats a confident guess. Use when research was
    inconclusive or the answer needs a human (e.g. ownership deeper than 3 hops)."""
    desk = _desk(tool_context)
    _state_append(tool_context, f"open_questions:{desk}", question)
    return "Noted."


# --- done -------------------------------------------------------------------


def done(reason: str, tool_context: ToolContext) -> str:
    """Close your desk. Call when every worklist item is either flagged, cleared, or
    noted as an open question — or when told your research budget is spent. reason is
    one sentence on why the desk is finished."""
    tool_context.actions.escalate = True
    return f"Desk closed: {reason}"


DESK_TOOLS = [
    read_scene,
    find_in_script,
    research,
    query_precedent,
    file_rating_prediction,
    file_flag,
    note_open_question,
    done,
]

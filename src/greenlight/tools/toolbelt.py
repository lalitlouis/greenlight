"""The desk toolbelt. Every gatekeeper gets these; desks differ only in instruction.

Docstrings are written for the model — ADK sends the signature and docstring as the
tool spec. Keep them imperative and concrete.

Design rules (see docs/TECH_SPEC.md):
- The citation invariant lives HERE, at the file_flag boundary, not in a prompt.
- research() is the only tool that spends money. It is budgeted and cached.
- done() is how a LoopAgent desk ends itself: it sets escalate.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
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

# --- clearance batching -----------------------------------------------------
# On entity-dense scripts one clearance conversation carrying 100+ case files
# went quadratic (p99 537s) and hallucination-prone. The desk now runs as up to
# CLEARANCE_MAX_BATCHES parallel batch agents named "clearance_counsel__bN",
# each with a bounded slice of the worklist and a FRESH conversation. Identity
# (_desk) stays "clearance_counsel"; every mutable per-desk key becomes
# per-AGENT to avoid the parallel state-delta races this codebase keeps paying
# for; readers aggregate with the desk_* helpers below.
CLEARANCE_BATCH_SIZE = 25
CLEARANCE_MAX_BATCHES = 4
_PROMINENCE_RANK = {"PLOT_CRITICAL": 0, "FEATURED": 1, "BACKGROUND": 2}


def _desk_name_of(agent_name: str) -> str:
    """Base desk enum for a desk or batch-agent name; the name itself otherwise."""
    for desk in DESKS:
        if agent_name.startswith(desk):
            return desk
    return agent_name


def batch_agent_names(desk: str) -> list[str]:
    """The base desk name plus its possible batch-agent names."""
    return [desk] + [f"{desk}__b{i}" for i in range(1, CLEARANCE_MAX_BATCHES + 1)]


def desk_flags(state: Any, desk: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name in batch_agent_names(desk):
        out.extend(state.get(f"flags:{name}") or [])
    return out


def desk_open_questions(state: Any, desk: str) -> list[Any]:
    out: list[Any] = []
    for name in batch_agent_names(desk):
        out.extend(state.get(f"open_questions:{name}") or [])
    return out


def desk_cleared(state: Any, desk: str) -> list[Any]:
    out: list[Any] = []
    for name in batch_agent_names(desk):
        out.extend(state.get(f"cleared:{name}") or [])
    return out


def desk_budget_left(state: Any, desk: str) -> int:
    batch_keys = [f"research_budget:{n}" for n in batch_agent_names(desk)[1:]]
    batch_vals = [state.get(k) for k in batch_keys]
    if any(v is not None for v in batch_vals):
        return sum(int(v) for v in batch_vals if v is not None)
    return int(state.get(f"research_budget:{desk}") or 0)


def _triage_dict(state: Any) -> dict[str, Any]:
    tri = state.get("triage") or {}
    if hasattr(tri, "model_dump"):
        tri = tri.model_dump()
    return tri


def clearance_batch_slices(state: Any) -> list[list[dict[str, Any]]]:
    """Deterministic partition of the clearance worklist: priority-sorted
    (PLOT_CRITICAL entities first), contiguous chunks, at most
    CLEARANCE_MAX_BATCHES — so batch 1 starts on the highest-stakes chases."""
    tri = _triage_dict(state)
    worklist = tri.get("clearance_counsel") or []
    rank = {
        e.get("entity_id"): _PROMINENCE_RANK.get(e.get("prominence"), 2)
        for e in tri.get("entities") or []
        if isinstance(e, dict)
    }
    ordered = sorted(
        list(worklist),
        key=lambda it: rank.get((it or {}).get("entity_id") or "", 1),
    )
    if not ordered:
        return []
    import math

    n_batches = min(CLEARANCE_MAX_BATCHES, max(1, math.ceil(len(ordered) / CLEARANCE_BATCH_SIZE)))
    size = math.ceil(len(ordered) / n_batches)
    return [ordered[i * size : (i + 1) * size] for i in range(n_batches)]


def batch_index(agent_name: str) -> int | None:
    """0-based batch index for a batch agent name; None for a plain desk."""
    if "__b" in agent_name:
        try:
            return int(agent_name.rsplit("__b", 1)[1]) - 1
        except ValueError:
            return None
    return None


_MAX_RESULTS_TO_MODEL = 6

_LOG = logging.getLogger("greenlight.tools")


# Live-API health, process-local for the same reason as _PROV_TEXTS (state
# deltas race under parallel tool calls). One bucket per run. The circuit
# breaker exists because a report produced with zero successful retrievals is
# worse than an honest failure — it looks real and is empty.
class RunAbortError(RuntimeError):
    """Deliberate whole-run abort. The tool-error shield lets this through:
    it exists precisely for failures where continuing would produce a report
    that looks real and is not (research API down)."""


_LIVE_STATS: dict[str, dict[str, int]] = {}
_LIVE_STATS_MAX_RUNS = 8
_BREAKER_CONSECUTIVE = 4


def _live_stats(tool_context: ToolContext) -> dict[str, int]:
    inv = str(getattr(tool_context, "invocation_id", "") or "run")
    if inv not in _LIVE_STATS and len(_LIVE_STATS) >= _LIVE_STATS_MAX_RUNS:
        _LIVE_STATS.pop(next(iter(_LIVE_STATS)))
    return _LIVE_STATS.setdefault(inv, {"ok": 0, "fail": 0, "consecutive": 0})


def _live_call_succeeded(tool_context: ToolContext) -> None:
    stats = _live_stats(tool_context)
    stats["ok"] += 1
    stats["consecutive"] = 0


def _live_call_failed(tool_context: ToolContext, api: str, exc: Exception) -> None:
    """Account one live-API failure: operator log, run-visible counter, breaker.

    Raises when the dependency looks down (consecutive failures, zero successes)
    so the run aborts honestly instead of shipping an unresearched report.
    """
    stats = _live_stats(tool_context)
    stats["fail"] += 1
    stats["consecutive"] += 1
    _LOG.warning("live %s call failed: %s", api, type(exc).__name__)
    state = tool_context.state
    state["research_failures"] = int(state.get("research_failures", 0)) + 1
    if stats["consecutive"] >= _BREAKER_CONSECUTIVE and stats["ok"] == 0:
        raise RunAbortError(
            f"research API unreachable ({stats['consecutive']} consecutive failures, "
            "none succeeded) — aborting rather than producing an unresearched report"
        ) from exc


_MAX_EXCERPT_CHARS = 1200
_MAX_EXTRACT_CHARS = 4000  # fetch_page returns one page, so it may run longer


def _desk(tool_context: ToolContext) -> str:
    name = tool_context.agent_name
    for desk in DESKS:
        if name.startswith(desk):
            return desk
    raise RuntimeError(f"tool called from unknown desk agent {name!r}")


def _agent_key(tool_context: ToolContext) -> str:
    """Full agent name — the write-scope for every mutable per-desk key.
    Batch agents get their own keys; parallel writers never share one."""
    return tool_context.agent_name


def _budget_key(tool_context: ToolContext) -> str:
    """Per-agent research budget key; batch agents lazily take their share of
    the desk budget, proportional to their slice of the worklist."""
    name = _agent_key(tool_context)
    desk = _desk(tool_context)
    if name == desk:
        return f"research_budget:{desk}"
    key = f"research_budget:{name}"
    state = tool_context.state
    if state.get(key) is None:
        import math

        slices = clearance_batch_slices(state)
        idx = batch_index(name)
        total_items = sum(len(x) for x in slices) or 1
        mine = len(slices[idx]) if idx is not None and idx < len(slices) else 0
        total_budget = int(state.get(f"research_budget:{desk}") or 0)
        state[key] = math.ceil(total_budget * mine / total_items) if mine else 0
    return key


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


def _live_search(
    objective: str,
    queries: list[str],
    session_id: str | None = None,
    country: str = "",
    include_domains: list[str] | None = None,
) -> dict[str, Any]:
    """The live Parallel Search call. Module-level so tests can monkeypatch it.

    This call is the partner-track requirement — it must stay on the default path.
    session_id groups every search in one analysis run: Parallel builds context
    across the chained questions (a song -> its composition owner -> its master),
    which is exactly how the desks work. country geo-targets results (the Territory
    desk searches FROM the territory); include_domains restricts to registries.
    """
    import parallel

    client = parallel.Parallel(api_key=os.environ["PARALLEL_API_KEY"])
    advanced: dict[str, Any] = {"max_results": 10}
    if country:
        advanced["location"] = country
    if include_domains:
        advanced["source_policy"] = {"include_domains": include_domains[:20]}
    res = client.search(
        search_queries=queries,
        objective=objective,
        mode="advanced",
        max_chars_total=8000,
        session_id=session_id,
        advanced_settings=advanced,
    )
    return res.model_dump()


def _durable_cache_load(key: str):
    """Indirection so tests replace it; production reads the GCS research cache."""
    try:
        from greenlight import storage

        return storage.load_research(key)
    except Exception:
        return None


def _durable_cache_store(key: str, record: dict[str, Any]) -> None:
    try:
        from greenlight import storage

        storage.save_research(key, record)
    except Exception:
        pass


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


async def research(
    objective: str,
    queries: list[str],
    entity_id: str,
    tool_context: ToolContext,
    country: str = "",
    restrict_to_domains: list[str] | None = None,
) -> dict[str, Any]:
    """Research a clearance question on the live web. Returns sourced, verbatim excerpts.

    objective: the actual clearance question, in full prose, self-contained — include
    the entity's script context (who, where, how depicted). This drives result quality.
    queries: 2-3 short keyword retrieval strings, 3-6 words each. Not sentences.
    entity_id: the worklist entity this research is for, e.g. "E003". Pass "" if the
    question is not about a single entity.
    country: OPTIONAL ISO 3166-1 alpha-2 code ("DE", "IN", "GB"). Set it when the
    question concerns one territory's rules, market, or sensibilities — the search is
    then geo-targeted to that country's web.
    restrict_to_domains: OPTIONAL domain allowlist for registry-grade checks. Use for
    authoritative-source questions: ["uspto.gov"] trademark status, ["ascap.com",
    "bmi.com", "sesac.com"] song registrations, ["copyright.gov"] registrations and
    renewals, ["courtlistener.com", "justia.com"] case law. Only these domains are
    searched, so never set it for general questions.

    Results are shared across desks — researching an already-researched entity is free.
    Every citation you file must copy an excerpt from these results VERBATIM. Never
    paraphrase an excerpt.
    """
    if isinstance(restrict_to_domains, str):
        cleaned = restrict_to_domains.strip()
        restrict_to_domains = (
            [cleaned] if cleaned and cleaned.lower() not in ("none", "null", "[]") else None
        )
    elif restrict_to_domains:
        restrict_to_domains = [
            str(d).strip()
            for d in restrict_to_domains
            if str(d).strip() and str(d).strip().lower() not in ("none", "null")
        ] or None

    # Key on entity AND question: an ownership chase asks several different
    # questions about one entity, and each deserves its own search. Identical
    # questions still share across desks. Geo/domain modifiers change the answer
    # set, so they join the key — but only when set, preserving old cache keys.
    modifiers = (
        f"|{country}|{sorted(restrict_to_domains or [])}"
        if (country or restrict_to_domains)
        else ""
    )
    q_hash = hashlib.sha1((objective + modifiers).encode()).hexdigest()[:12]
    key = f"research:{entity_id}:{q_hash}" if entity_id else f"research:{q_hash}"
    cached = tool_context.state.get(key)
    if cached is not None:
        _register_provenance(
            tool_context,
            [x for r in cached["results"] for x in [r.get("title", ""), *r.get("excerpts", [])]],
        )
        return {"cached": True, "results": cached["results"], "search_id": cached["search_id"]}

    # Cross-run cache: identical questions reuse identical sources for a week.
    # Reruns of the same script then show the verifier the same evidence —
    # score stability — and the API is paid once per question, not per run.
    stored = await asyncio.to_thread(
        _durable_cache_load, q_hash if not entity_id else f"{entity_id}-{q_hash}"
    )
    if stored is not None:
        tool_context.state[key] = {k: v for k, v in stored.items() if not k.startswith("_")}
        _index_research_key(tool_context, key)
        _register_provenance(
            tool_context,
            [x for r in stored["results"] for x in [r.get("title", ""), *r.get("excerpts", [])]],
        )
        return {"cached": True, "results": stored["results"], "search_id": stored["search_id"]}

    budget_key = _budget_key(tool_context)
    budget = int(tool_context.state.get(budget_key, 0))
    if budget <= 0:
        return {
            "error": "research budget spent",
            "guidance": (
                "File flags you can already support with earlier results, record what "
                "you could not resolve with note_open_question, then call done()."
            ),
        }

    session_id = f"scriptrisk-{getattr(tool_context, 'invocation_id', '') or 'run'}"[:64]
    # Decrement BEFORE the await: when a desk issues several research calls in
    # one turn they run concurrently, and the budget must count each of them.
    tool_context.state[budget_key] = budget - 1
    try:
        raw = await asyncio.to_thread(
            _live_search,
            objective,
            queries,
            session_id=session_id,
            country=country,
            include_domains=restrict_to_domains,
        )
    except Exception as exc:  # a failed search costs nothing; the failure is accounted
        tool_context.state[budget_key] = budget
        _live_call_failed(tool_context, "search", exc)
        return {
            "error": f"search failed: {type(exc).__name__}",
            "guidance": "Try again with different queries, or note an open question.",
        }
    _live_call_succeeded(tool_context)
    compacted = _compact(raw)
    record = {
        "objective": objective,
        "search_id": raw.get("search_id", ""),
        "results": compacted,
    }
    tool_context.state[key] = record
    _index_research_key(tool_context, key)
    _register_provenance(
        tool_context,
        [x for r in compacted for x in [r.get("title", ""), *r.get("excerpts", [])]],
    )
    await asyncio.to_thread(
        _durable_cache_store, q_hash if not entity_id else f"{entity_id}-{q_hash}", record
    )
    return {
        "cached": False,
        "budget_remaining": budget - 1,
        "search_id": record["search_id"],
        "results": compacted,
    }


# --- fetch_page (Parallel Extract API) --------------------------------------


def _live_extract(urls: list[str], objective: str, session_id: str | None = None) -> dict[str, Any]:
    """The live Parallel Extract call — full-page retrieval. Module-level for tests."""
    import parallel

    client = parallel.Parallel(api_key=os.environ["PARALLEL_API_KEY"])
    res = client.extract(
        urls=urls, objective=objective, max_chars_total=12000, session_id=session_id
    )
    return res.model_dump()


async def fetch_page(url: str, objective: str, tool_context: ToolContext) -> dict[str, Any]:
    """Fetch ONE specific web page and return its relevant content as verbatim excerpts.

    Use when a research() result names a promising source but its excerpt is too thin
    to cite — a PRO repertory entry, a rights-holder or publisher page, a court record,
    a safety regulation. url: the exact page, copied from a research() result.
    objective: what you need from that page, one sentence.

    Costs 1 research budget. The excerpts are citable exactly like research() excerpts —
    copy them VERBATIM when you file.
    """
    key = "extract:" + hashlib.sha1(f"{url}|{objective}".encode()).hexdigest()[:12]
    cached = tool_context.state.get(key)
    if cached is not None:
        _register_provenance(
            tool_context,
            [x for r in cached["results"] for x in [r.get("title") or "", *r.get("excerpts", [])]],
        )
        return {"cached": True, "results": cached["results"]}

    stored = await asyncio.to_thread(_durable_cache_load, key)
    if stored is not None:
        tool_context.state[key] = {k: v for k, v in stored.items() if not k.startswith("_")}
        _index_research_key(tool_context, key)
        _register_provenance(
            tool_context,
            [x for r in stored["results"] for x in [r.get("title") or "", *r.get("excerpts", [])]],
        )
        return {"cached": True, "results": stored["results"]}

    budget_key = _budget_key(tool_context)
    budget = int(tool_context.state.get(budget_key, 0))
    if budget <= 0:
        return {
            "error": "research budget spent",
            "guidance": (
                "File flags you can already support with earlier results, record what "
                "you could not resolve with note_open_question, then call done()."
            ),
        }
    tool_context.state[budget_key] = budget - 1
    session_id = f"scriptrisk-{getattr(tool_context, 'invocation_id', '') or 'run'}"[:64]
    try:
        raw = await asyncio.to_thread(_live_extract, [url], objective, session_id=session_id)
    except Exception as exc:  # page fetch can fail on robots/paywalls — refund, keep working
        tool_context.state[budget_key] = budget
        _live_call_failed(tool_context, "extract", exc)
        return {
            "error": f"fetch failed: {type(exc).__name__}",
            "guidance": "Use the research() excerpts you already have, or try another source.",
        }
    _live_call_succeeded(tool_context)
    results = []
    for r in raw.get("results", []):
        excerpts, used = [], 0
        for ex in r.get("excerpts", []):
            if used >= _MAX_EXTRACT_CHARS:
                break
            excerpts.append(ex[: _MAX_EXTRACT_CHARS - used])
            used += len(ex)
        results.append(
            {
                "url": r["url"],
                "title": r.get("title"),
                "publish_date": r.get("publish_date"),
                "excerpts": excerpts,
            }
        )
    if not results:
        tool_context.state[budget_key] = budget  # nothing usable: refund
        errs = [
            e.get("error_type") or e.get("message") or "unavailable" for e in raw.get("errors", [])
        ]
        return {
            "error": f"page not retrievable: {'; '.join(str(e) for e in errs) or 'no content'}",
            "guidance": "Use the research() excerpts you already have, or try another source.",
        }
    record = {"objective": objective, "results": results}
    tool_context.state[key] = record
    _index_research_key(tool_context, key)
    _register_provenance(
        tool_context,
        [x for r in results for x in [r.get("title") or "", *r.get("excerpts", [])]],
    )
    await asyncio.to_thread(_durable_cache_store, key, record)
    return {"cached": False, "budget_remaining": budget - 1, "results": results}


# --- deep_research (Parallel Task API) --------------------------------------


def _live_task(question: str, processor: str) -> dict[str, Any]:
    """The live Parallel Task API call — deep multi-source research. Module-level for tests."""
    import parallel

    client = parallel.Parallel(api_key=os.environ["PARALLEL_API_KEY"])
    res = client.task_run.execute(
        input=question,
        processor=processor,
        output=(
            "A clearance research memo that directly answers the question. State the "
            "resolved facts (owners, registrations, status, dates) plainly, say what "
            "could not be verified, and support every fact with source citations "
            "carrying verbatim excerpts."
        ),
        timeout=900,
    )
    return res.model_dump()


_DEEP_COST = 3  # a deep run replaces several searches; price it that way
_DEEP_MAX_PER_DESK = 2


async def deep_research(question: str, entity_id: str, tool_context: ToolContext) -> dict[str, Any]:
    """Escalate ONE hard, unresolved question to a deep multi-source web investigation.

    Slow (several minutes) and thorough — a research analyst, not a search. Use ONLY
    when research() has twice failed to resolve a question that decides a potential
    BLOCKER or HIGH finding: an ownership chain (composition vs master, publisher
    splits, PRO registration), a rights-holder plain search cannot locate, a
    conflicting-rights puzzle. Never for a first pass, never for LOW/FYI questions.

    question: fully self-contained prose — all script context, what you already know,
    and exactly which facts would resolve it. entity_id: the worklist entity ("E003"),
    or "" if not entity-specific.

    Costs 3 research budget; at most 2 calls per desk per run. Citation excerpts in
    the result are citable exactly like research() excerpts — copy them VERBATIM.
    """
    key = "deep:" + hashlib.sha1(question.encode()).hexdigest()[:12]
    cached = tool_context.state.get(key)
    if cached is None:
        cached = await asyncio.to_thread(_durable_cache_load, key)
        if cached is not None:
            tool_context.state[key] = {k: v for k, v in cached.items() if not k.startswith("_")}
            _index_research_key(tool_context, key)
    if cached is not None:
        _register_provenance(
            tool_context,
            [cached.get("answer", "")]
            + [x for c in cached.get("citations", []) for x in c.get("excerpts", [])],
        )
        return {
            "cached": True,
            "answer": cached.get("answer"),
            "citations": cached.get("citations"),
        }

    used_key = f"deep_used:{_agent_key(tool_context)}"
    used = int(tool_context.state.get(used_key, 0))
    if used >= _DEEP_MAX_PER_DESK:
        return {
            "error": "deep research allowance spent for this desk",
            "guidance": "Use research(), or note the question with note_open_question.",
        }
    budget_key = _budget_key(tool_context)
    budget = int(tool_context.state.get(budget_key, 0))
    if budget < _DEEP_COST:
        return {
            "error": f"deep research costs {_DEEP_COST} budget; {budget} remains",
            "guidance": "Note the question with note_open_question and finish the worklist.",
        }
    tool_context.state[used_key] = used + 1
    tool_context.state[budget_key] = budget - _DEEP_COST
    processor = os.getenv("PARALLEL_TASK_PROCESSOR", "core")
    try:
        raw = await asyncio.to_thread(_live_task, question, processor)
    except Exception as exc:  # slow-path API failure: refund; the allowance stays spent
        tool_context.state[budget_key] = budget
        _live_call_failed(tool_context, "task", exc)
        return {
            "error": f"deep research failed: {type(exc).__name__}",
            "guidance": "Fall back to research(), or note an open question.",
        }
    _live_call_succeeded(tool_context)
    output = raw.get("output") or {}
    answer = output.get("content") if isinstance(output.get("content"), str) else ""
    citations, seen = [], set()
    for basis in output.get("basis") or []:
        for cit in basis.get("citations") or []:
            u = _normalize_url(cit.get("url", ""))
            if not u or u in seen:
                continue
            seen.add(u)
            excerpts, used_c = [], 0
            for ex in cit.get("excerpts") or []:
                if used_c >= _MAX_EXCERPT_CHARS:
                    break
                excerpts.append(ex[: _MAX_EXCERPT_CHARS - used_c])
                used_c += len(ex)
            citations.append(
                {"url": cit.get("url"), "title": cit.get("title"), "excerpts": excerpts}
            )
    record = {"question": question, "answer": answer, "citations": citations}
    tool_context.state[key] = record
    _index_research_key(tool_context, key)
    _register_provenance(
        tool_context,
        [answer] + [x for c in citations for x in [c.get("title") or "", *c.get("excerpts", [])]],
    )
    await asyncio.to_thread(_durable_cache_store, key, record)
    return {
        "cached": False,
        "budget_remaining": budget - _DEEP_COST,
        "answer": answer,
        "citations": citations,
    }


# --- file_flag --------------------------------------------------------------


# Provenance registry, OUT of ADK state: session-state deltas merge last-writer-
# wins even for parallel tool calls in one turn, so any mutable index there loses
# entries under concurrency (49 false provenance rejections in one eval run). A
# run executes in a single process (worker job or in-process task), so a plain
# module dict keyed by invocation id is race-free on the event loop and shared
# by every desk. State-based indices remain as a secondary source.
_PROV_TEXTS: dict[str, list[str]] = {}
_PROV_MAX_RUNS = 8


def _prov_bucket(tool_context: ToolContext) -> list[str]:
    inv = str(getattr(tool_context, "invocation_id", "") or "run")
    if inv not in _PROV_TEXTS and len(_PROV_TEXTS) >= _PROV_MAX_RUNS:
        _PROV_TEXTS.pop(next(iter(_PROV_TEXTS)))  # drop the oldest run's registry
    return _PROV_TEXTS.setdefault(inv, [])


def _register_provenance(tool_context: ToolContext, texts: list[str]) -> None:
    bucket = _prov_bucket(tool_context)
    bucket.extend(_norm_for_match(x) for x in texts if x)
    # excerpts arrive as storage chunks; a desk quoting across a chunk boundary
    # is still verbatim — register the joined text as well
    joined = " ".join(x for x in texts if x)
    if joined:
        bucket.append(_norm_for_match(joined))


def _index_research_key(tool_context: ToolContext, key: str) -> None:
    """Explicit index of research state keys, ONE PER AGENT. ADK State cannot be
    enumerated (.keys() crashed in production), and a single shared list gets
    clobbered by concurrent desk branches (last-writer-wins on parallel state
    deltas — desks were erasing each other's entries, making legitimate
    excerpts fail provenance). Per-desk keys mean no two branches ever write
    the same key; the read side unions all four. This function is sync with no
    awaits, so same-desk concurrent tool calls can't interleave the append."""
    index_key = f"research_keys:{_agent_key(tool_context)}"
    keys = list(tool_context.state.get(index_key, []))
    if key not in keys:
        keys.append(key)
        tool_context.state[index_key] = keys


def _norm_for_match(s: str) -> str:
    """Whitespace/quote-insensitive form for provenance matching: collapse runs of
    whitespace, normalize curly quotes and dashes, lowercase. Deliberately NOT
    fuzzy beyond that — paraphrase must fail."""
    pairs = (
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u2014", "-"),
        ("\u2013", "-"),
        ("\u2026", "..."),
    )
    for a, b in pairs:
        s = s.replace(a, b)
    return " ".join(s.split()).lower()


_MIN_PROVENANCE_CHARS = 12  # shorter quotes match anything; the verifier judges those


_OVERLAP_MIN_WORDS = 8
_OVERLAP_RATIO = 0.9


def _word_overlap_hit(needle: str, texts: list[str]) -> bool:
    """Secondary standard: a quote stitched or elided from ONE real source keeps
    ~all its words; a fabricated quote does not. >=90% of the needle's words in
    a single registered text = provenance, exact ordering not required."""
    min_word_len = 3  # skip stopword-length tokens
    words = [w for w in needle.split() if len(w) >= min_word_len]
    if len(words) < _OVERLAP_MIN_WORDS:
        return False
    need = set(words)
    for text in texts:
        tw = set(text.split())
        if len(need & tw) / len(need) >= _OVERLAP_RATIO:
            return True
    return False


_REPAIR_MIN_WORDS = 6
_REPAIR_RATIO = 0.6  # 60-90%% overlap = paraphrase of a real retrieval; repairable
_HANDBACK_RATIO = 0.25


def _overlap_ratio(needle: str, candidate: str) -> float:
    """Share of the needle's substantive words present in the candidate."""
    min_word_len = 3
    words = [w for w in _norm_for_match(needle).split() if len(w) >= min_word_len]
    if len(words) < _REPAIR_MIN_WORDS:
        return 0.0
    need = set(words)
    cand = set(_norm_for_match(candidate).split())
    return len(need & cand) / len(need)


def _best_registry_match(attempt: str, tool_context: ToolContext) -> str | None:
    """The registered text the model was clearly reaching for, if any.

    >=60% of the attempted quote's words in one registered text means the model
    paraphrased a real retrieval (markdown stripped, line breaks normalized, a
    word dropped) — hand the true verbatim text back so the FINDING survives the
    FORMALITY. Below that, nothing retrieved resembles the quote: no repair.
    """
    best, best_r = None, 0.0
    for text in _prov_bucket(tool_context):
        r = _overlap_ratio(attempt, text)
        if r > best_r:
            best, best_r = text, r
    return best[:800] if best is not None and best_r >= _REPAIR_RATIO else None


def _handback_candidates(attempts: list[str], tool_context: ToolContext) -> list[str]:
    """Closest registered texts to the failed quotes — race-free, from the
    process registry — offered back in the rejection for verbatim copying."""
    scored: list[tuple[float, str]] = []
    for text in _prov_bucket(tool_context):
        r = max((_overlap_ratio(a, text) for a in attempts), default=0.0)
        if r >= _HANDBACK_RATIO:
            scored.append((r, text))
    scored.sort(key=lambda x: -x[0])
    return [t[:400] for _, t in scored[:3]]


# Same-flag retry ledger, process-local (state counters race under parallel
# tool calls — the provenance saga). Bounds the worst case: 33 consecutive
# rejections of one Winklevoss filing burned a desk's whole tail (2026-08-26).
# Flag ids allocated process-locally: a run executes in one process, and a
# state-based counter loses increments under parallel batch writers. Gaps from
# rejected filings are harmless; collisions are not.
_FLAG_SEQ: dict[str, int] = {}
_FLAG_SEQ_MAX = 4096


def _next_flag_seq(tool_context: ToolContext, desk: str) -> int:
    # Key by invocation id ONLY: the ADK runtime hands tools a FRESH state
    # wrapper per call, so id(state) reset the counter on every filing and one
    # run shipped every safety flag as F301 (2026-08-26). The invocation id is
    # stable for the whole run; id(state) survives only as the test fallback.
    inv = str(getattr(tool_context, "invocation_id", "") or "")
    key = f"{inv}:{desk}" if inv else f"{id(tool_context.state)}:{desk}"
    if key not in _FLAG_SEQ and len(_FLAG_SEQ) >= _FLAG_SEQ_MAX:
        _FLAG_SEQ.pop(next(iter(_FLAG_SEQ)))
    _FLAG_SEQ[key] = _FLAG_SEQ.get(key, 0) + 1
    return _FLAG_SEQ[key]


_REJECT_COUNTS: dict[str, int] = {}
_REJECT_MAX_RUNS = 4096
_PROV_RETRY_LIMIT = 4


def _reject_or_stop(tool_context: ToolContext, entity_id: str, category: str, msg: str) -> str:
    """Route EVERY file_flag rejection through one retry ledger. The provenance
    path was capped but a contract-schema loop ran 62 identical retries
    (E030, 2026-08-26) through the uncapped branch — any rejection repeated
    _PROV_RETRY_LIMIT times becomes the hard stop, whatever its cause."""
    tries = _reject_count_bump(tool_context, entity_id, category)
    if tries >= _PROV_RETRY_LIMIT:
        return (
            "REJECTED, not filed — and DO NOT retry this flag: after "
            f"{tries} attempts it still fails validation for the same reasons. "
            "Record the issue with note_open_question (state what you believe and "
            "why it could not be filed) and move to your next worklist item NOW."
        )
    return msg


def _reject_count_bump(tool_context: ToolContext, entity_id: str, category: str) -> int:
    inv = str(getattr(tool_context, "invocation_id", "") or "run")
    key = f"{inv}:{_desk(tool_context)}:{entity_id}:{category}"
    if key not in _REJECT_COUNTS and len(_REJECT_COUNTS) >= _REJECT_MAX_RUNS:
        _REJECT_COUNTS.pop(next(iter(_REJECT_COUNTS)))
    _REJECT_COUNTS[key] = _REJECT_COUNTS.get(key, 0) + 1
    return _REJECT_COUNTS[key]


def _quotable_excerpts(entity_id: str, tool_context: ToolContext, limit: int = 3) -> list[str]:
    """The registered research excerpts for one entity, for rejection self-healing.

    Reads via the per-desk research-key indices — NEVER by iterating state keys
    (ADK's State does not support it; see the provenance saga). Excerpts are
    returned as 400-char heads: a head is a substring of the registered text, so
    a citation copied from it passes the verbatim gate.
    """
    if not entity_id:
        return []
    state = tool_context.state
    keys: list[str] = []
    for d in DESKS:
        for n in batch_agent_names(d):
            for k in state.get(f"research_keys:{n}") or []:
                if isinstance(k, str) and k.startswith(f"research:{entity_id}:") and k not in keys:
                    keys.append(k)
    out: list[str] = []
    for k in keys:
        rec = state.get(k) or {}
        for r in rec.get("results", []):
            for ex in r.get("excerpts", []):
                if ex and ex.strip():
                    out.append(ex[:400])
                    if len(out) >= limit:
                        return out
    return out


def _excerpt_exists(excerpt: str, tool_context: ToolContext) -> bool:
    needle = _norm_for_match(excerpt).strip(" \"'.…-")
    if len(needle) < _MIN_PROVENANCE_CHARS:
        return True
    # 1. the process-local registry — the authoritative source
    bucket = _PROV_TEXTS.get(str(getattr(tool_context, "invocation_id", "") or "run"), [])
    for text in bucket:
        if needle in text:
            return True
    if _word_overlap_hit(needle, bucket):
        return True
    if os.getenv("GREENLIGHT_PROV_DEBUG"):
        with open("/tmp/prov_debug.jsonl", "a") as fh:
            import json as _json

            fh.write(_json.dumps({"needle": needle[:400], "bucket_n": len(bucket)}) + "\n")
    return _exists_in_state(needle, tool_context.state)


def _exists_in_state(needle: str, state: Any) -> bool:
    """Secondary provenance sources kept in session state: the script itself,
    per-desk research indices, and precedent rationales."""
    if needle in _norm_for_match(state.get("source") or ""):
        return True
    seen: set[str] = set()
    for desk in DESKS:
        for name in batch_agent_names(desk):
            for key in state.get(f"research_keys:{name}", []):
                if key in seen:
                    continue
                seen.add(key)
                rec = state.get(key) or {}
                for r in rec.get("results", []):
                    for ex in r.get("excerpts", []):
                        if needle in _norm_for_match(ex):
                            return True
                    if needle in _norm_for_match(r.get("title", "")):
                        return True
    return _precedent_has(needle, state)


def _precedent_has(needle: str, state: Any) -> bool:
    for desk in DESKS:
        for name in batch_agent_names(desk):
            for comp in state.get(f"last_precedent:{name}") or []:
                if needle in _norm_for_match(comp.get("rationale", "")):
                    return True
    return False


BACKGROUND_HOSTS = {
    "wikipedia.org",
    "fandom.com",
    "reddit.com",
    "quora.com",
    "discogs.com",
    "songfacts.com",
    "secondhandsongs.com",
    "imdb.com",
    "tvtropes.org",
    "writing.stackexchange.com",
    "writingforums.com",
    "genius.com",
    "looper.com",
}

_SCENE_ANCHOR_CAP = 8  # a finding spanning more scenes than this says "the script"


def _is_background_host(url: str) -> bool:
    seg = (url or "").split("/")[2:3]
    if not seg:
        return True
    host = seg[0].removeprefix("www.")
    root = ".".join(host.split(".")[-2:])
    return host in BACKGROUND_HOSTS or root in BACKGROUND_HOSTS


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
    seq = _next_flag_seq(tool_context, desk)

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
        return _reject_or_stop(
            tool_context,
            entity_id,
            category,
            "REJECTED, not filed. Fix ALL of these and refile once:\n- " + "\n- ".join(e.errors),
        )

    if not all(c["excerpt"].strip() for c in cits):
        return _reject_or_stop(
            tool_context,
            entity_id,
            category,
            "REJECTED, not filed: every citation needs a non-empty verbatim excerpt.",
        )

    # One finding per entity, anchored where the issue occurs. Ratings and
    # territory findings legitimately aggregate cumulative content; everything
    # else spanning the whole script is an umbrella flag that swallows real
    # entities (the F101 failure: 137 scenes, twelve people, one finding).
    aggregate_ok = category.startswith(("rating_", "territory_"))
    if len(scene_ids) > _SCENE_ANCHOR_CAP and not aggregate_ok:
        return _reject_or_stop(
            tool_context,
            entity_id,
            category,
            f"REJECTED, not filed: this finding anchors to {len(scene_ids)} scenes. "
            f"Anchor to the {_SCENE_ANCHOR_CAP} scenes where the issue is strongest. "
            "If several distinct entities share this issue, file ONE FINDING PER "
            "ENTITY — each named person, brand, or work gets its own finding with "
            "its own citations and remedy.",
        )

    # A legal conclusion needs at least one non-background source. Fan wikis and
    # forums may inform, but they cannot carry a MEDIUM+ finding alone.
    if severity in ("BLOCKER", "HIGH", "MEDIUM") and all(
        _is_background_host(c.get("url") or "") for c in cits
    ):
        return _reject_or_stop(
            tool_context,
            entity_id,
            category,
            "REJECTED, not filed: every citation is a background-tier source (fan "
            "wiki, forum, general-interest site). A finding at this severity needs "
            "at least one authoritative source — regulator or government site, "
            "USPTO/Copyright Office, CSATF, CARA/filmratings.com, BBFC, primary "
            "statutes, or law-firm analysis. Re-run research() with "
            "restrict_to_domains targeting those, or lower the severity to LOW/FYI "
            "if the claim only merits background support.",
        )

    # Excerpt provenance: a citation's excerpt must exist VERBATIM in material this
    # run actually retrieved (research results, precedent rationales, or the script
    # itself). A model deep in a long run can confabulate a plausible "quote"; this
    # check is deterministic and closes that door — the verifier judges relevance,
    # this judges existence.
    # Excerpt provenance with AUTO-REPAIR: the desk's finding must not die on a
    # transcription formality. A near-miss quote (>=60% of its words in one
    # registered text) is the model paraphrasing a real retrieval — substitute
    # the true verbatim text and file; the blinded verifier still judges whether
    # that text supports the claim. Only quotes resembling NOTHING retrieved are
    # rejected — and after _PROV_RETRY_LIMIT tries, retrying is refused so a
    # desk can never again burn its tail on one filing.
    repaired = 0
    still_bad: list[str] = []
    for c in cits:
        if _excerpt_exists(c["excerpt"], tool_context):
            continue
        fix = _best_registry_match(c["excerpt"], tool_context)
        if fix is not None:
            c["excerpt"] = fix
            repaired += 1
        else:
            still_bad.append(c["excerpt"][:60])
    if still_bad:
        msg = (
            "REJECTED, not filed: these excerpts do not appear verbatim in any research "
            "result, precedent rationale, or the script — re-copy them exactly from your "
            "tool results, character for character:\n- " + "\n- ".join(still_bad)
        )
        quotable = _handback_candidates(still_bad, tool_context) or _quotable_excerpts(
            entity_id, tool_context
        )
        if quotable:
            msg += (
                "\n\nVERBATIM excerpts on record — copy from these EXACTLY (any "
                "contiguous part):\n" + "\n".join(f"<<{q}>>" for q in quotable)
            )
        return _reject_or_stop(tool_context, entity_id, category, msg)

    known = {s["scene_id"] for s in tool_context.state.get("scenes", [])}
    if bad := [s for s in scene_ids if s not in known]:
        return _reject_or_stop(
            tool_context,
            entity_id,
            category,
            f"REJECTED, not filed: unknown scene ids {bad}. Use ids from your worklist.",
        )

    _state_append(tool_context, f"flags:{_agent_key(tool_context)}", flag)
    note = (
        f" ({repaired} citation excerpt{'s' if repaired != 1 else ''} auto-corrected "
        "to the verbatim source text)"
        if repaired
        else ""
    )
    return f"Filed {flag['flag_id']} ({severity} {category}).{note}"


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
    """Embed text with Vertex — must match the model used at corpus ingest time.
    Pinned to its own region: text-embedding-005 is not served from the global
    endpoint that the Gemini calls use for DSQ headroom."""
    from google import genai

    client = genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("EMBED_LOCATION", "us-central1"),
    )
    res = client.models.embed_content(model="text-embedding-005", contents=text)
    return list(res.embeddings[0].values)


_BASE_RATES_CACHE: dict[str, dict[str, float]] = {}


def _corpus_base_rates() -> dict[str, float]:
    """Rating distribution across the whole corpus — the denominator that tells
    the reader whether the neighbours add lift over the base rate."""
    if "rates" not in _BASE_RATES_CACHE:
        try:
            rows = (
                _clickhouse_client()
                .query("SELECT rating, count() FROM rating_rationales GROUP BY rating")
                .result_rows
            )
            total = sum(int(c) for _, c in rows) or 1
            _BASE_RATES_CACHE["rates"] = {r: round(100 * int(c) / total, 1) for r, c in rows}
        except Exception:
            _BASE_RATES_CACHE["rates"] = {}
    return _BASE_RATES_CACHE["rates"]


async def query_precedent(text: str, k: int, tool_context: ToolContext) -> dict[str, Any]:
    """Find the k nearest released films in a corpus of 6,302 rated releases.

    text: a capsule profile of THIS script, 2-3 sentences, in this order:
      1. GENRE, REGISTER, AND SETTING FIRST — "a dialogue-driven biographical
         drama about a corporate founding, told through legal depositions",
         "a slow-burn rural ghost story", "an ensemble heist comedy". The
         corpus is embedded from film descriptions, so genre and tone are what
         place you in the right neighbourhood.
      2. THEN the rating-relevant content elements with their framing —
         "pervasive strong language; brief cocaine use at a party, not
         endorsed; no violence; no nudity". Framing matters: depicted-vs-
         endorsed and on-screen-vs-recounted change ratings.
    A bare content list ("sex, drugs, language") lands you among shock
    comedies regardless of genre — always lead with what kind of film this is.
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
        vec = await asyncio.to_thread(_embed, text)
        rows = await asyncio.to_thread(
            lambda: (
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
        )
    except Exception as e:
        return {
            "error": f"precedent corpus unavailable: {type(e).__name__}: {str(e)[:120]}",
            "guidance": "Fall back to research() on documented CARA standards.",
        }
    base_rates = _corpus_base_rates()
    dists = [float(r[5]) for r in rows]
    spread = round(max(dists) - min(dists), 4) if dists else 0.0
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
    tool_context.state[f"last_precedent:{_agent_key(tool_context)}"] = comparables
    tool_context.state[f"last_precedent_meta:{_agent_key(tool_context)}"] = {
        "base_rates": base_rates,
        "spread": spread,
    }
    _register_provenance(tool_context, [c.get("rationale", "") for c in comparables])
    out: dict[str, Any] = {"comparables": comparables, "corpus_base_rates": base_rates}
    if spread and spread < 0.05:  # noqa: PLR2004 - tight-cluster caution threshold
        out["caution"] = (
            f"distances span only {spread} — the neighbourhood is not discriminating "
            "strongly; weigh the corpus base rate as much as the neighbours"
        )
    return out


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
    meta = tool_context.state.get(f"last_precedent_meta:{desk}") or {}
    tool_context.state["rating_prediction"] = {
        "predicted": predicted,
        "target": tool_context.state.get("target_rating"),
        "rationale": rationale,
        "comparables": comparables,
        "beats_to_cut": list(beats_to_cut),
        "corpus_base_rates": meta.get("base_rates") or {},
        "distance_spread": meta.get("spread"),
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
    _state_append(tool_context, f"open_questions:{_agent_key(tool_context)}", question)
    return "Noted."


# --- done -------------------------------------------------------------------


_DONE_MAX_REFUSALS = 2
_DONE_MIN_BUDGET = 3
_DONE_COVERAGE = 0.5


def record_clearance(entity_id: str, reasoning: str, tool_context: ToolContext) -> str:
    """Record that a worklist item was examined and CLEARED — no finding needed.

    This is how examined-and-fine work becomes visible: silence looks identical to
    "never looked". Use it for every worklist item you investigated and concluded
    carries no issue (public domain, generic term, protected expressive use, no
    real-world match). NOT for unresolved items — those are note_open_question.

    entity_id: the worklist entity this clears (e.g. "E014"), or "" for a
      script-level determination.
    reasoning: one or two sentences stating WHY it is clear, specific enough for
      production counsel to audit ("'Amazing Grace' composition published 1779,
      public domain worldwide; no specific recording is used").
    """
    desk = _desk(tool_context)
    name = _agent_key(tool_context)
    state = tool_context.state
    entry = {"entity_id": entity_id or None, "reasoning": (reasoning or "").strip()[:600]}
    if not entry["reasoning"]:
        return "REJECTED: reasoning is required — a bare 'cleared' is not auditable."
    cleared = list(state.get(f"cleared:{name}", []) or [])
    cleared.append(entry)
    state[f"cleared:{name}"] = cleared
    return f"Recorded: {desk} cleared {entity_id or 'script-level item'}."


def done(reason: str, tool_context: ToolContext) -> str:
    """Close your desk. Call when every worklist item is either flagged, cleared, or
    noted as an open question — or when told your research budget is spent. reason is
    one sentence on why the desk is finished.

    Closing is refused when substantial worklist coverage is missing while research
    budget remains — address the remaining items or note them as open questions first.
    """
    desk = _desk(tool_context)
    name = _agent_key(tool_context)
    state = tool_context.state
    # Mechanical closing contract: a desk that filed dispositions for less than
    # half its worklist, with budget still in hand, is quitting early — a failure
    # mode the eval kept catching. Enforce it here, not in prose. Two refusals
    # max: after that, close (the LoopAgent iteration cap is the hard stop).
    # A clearance batch is judged against ITS slice, with its own keys.
    refusals = int(state.get(f"done_refusals:{name}", 0))
    idx = batch_index(name)
    if idx is not None:
        slices = clearance_batch_slices(state)
        worklist = slices[idx] if idx < len(slices) else []
    else:
        worklist = _triage_dict(state).get(desk) or []
    budget_left = int(state.get(_budget_key(tool_context), 0))
    dispositions = (
        len(state.get(f"flags:{name}", []) or [])
        + len(state.get(f"open_questions:{name}", []) or [])
        + len(state.get(f"cleared:{name}", []) or [])
    )
    underworked = worklist and dispositions < _DONE_COVERAGE * len(worklist)
    if underworked and budget_left >= _DONE_MIN_BUDGET and refusals < _DONE_MAX_REFUSALS:
        state[f"done_refusals:{name}"] = refusals + 1
        return (
            f"NOT CLOSED: you have addressed {dispositions} of {len(worklist)} worklist "
            f"items and {budget_left} research budget remains. Work the remaining items — "
            "file, or note_open_question each one — then call done() again."
        )
    tool_context.actions.escalate = True
    return f"Desk closed: {reason}"


DESK_TOOLS = [
    read_scene,
    find_in_script,
    research,
    record_clearance,
    fetch_page,
    deep_research,
    query_precedent,
    file_rating_prediction,
    file_flag,
    note_open_question,
    done,
]

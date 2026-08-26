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
    desk = _desk(tool_context)
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

    used_key = f"deep_used:{desk}"
    used = int(tool_context.state.get(used_key, 0))
    if used >= _DEEP_MAX_PER_DESK:
        return {
            "error": "deep research allowance spent for this desk",
            "guidance": "Use research(), or note the question with note_open_question.",
        }
    budget_key = f"research_budget:{desk}"
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
    """Explicit index of research state keys, ONE PER DESK. ADK State cannot be
    enumerated (.keys() crashed in production), and a single shared list gets
    clobbered by concurrent desk branches (last-writer-wins on parallel state
    deltas — desks were erasing each other's entries, making legitimate
    excerpts fail provenance). Per-desk keys mean no two branches ever write
    the same key; the read side unions all four. This function is sync with no
    awaits, so same-desk concurrent tool calls can't interleave the append."""
    index_key = f"research_keys:{_desk(tool_context)}"
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
        for key in state.get(f"research_keys:{desk}", []):
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
    for desk in DESKS:
        for comp in state.get(f"last_precedent:{desk}") or []:
            if needle in _norm_for_match(comp.get("rationale", "")):
                return True
    return False


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

    # Excerpt provenance: a citation's excerpt must exist VERBATIM in material this
    # run actually retrieved (research results, precedent rationales, or the script
    # itself). A model deep in a long run can confabulate a plausible "quote"; this
    # check is deterministic and closes that door — the verifier judges relevance,
    # this judges existence.
    fabricated = [
        c["excerpt"][:60] for c in cits if not _excerpt_exists(c["excerpt"], tool_context)
    ]
    if fabricated:
        tool_context.state[seq_key] = seq - 1
        return (
            "REJECTED, not filed: these excerpts do not appear verbatim in any research "
            "result, precedent rationale, or the script — re-copy them exactly from your "
            "tool results, character for character:\n- " + "\n- ".join(fabricated)
        )

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


async def query_precedent(text: str, k: int, tool_context: ToolContext) -> dict[str, Any]:
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
    _register_provenance(tool_context, [c.get("rationale", "") for c in comparables])
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


_DONE_MAX_REFUSALS = 2
_DONE_MIN_BUDGET = 3
_DONE_COVERAGE = 0.5


def done(reason: str, tool_context: ToolContext) -> str:
    """Close your desk. Call when every worklist item is either flagged, cleared, or
    noted as an open question — or when told your research budget is spent. reason is
    one sentence on why the desk is finished.

    Closing is refused when substantial worklist coverage is missing while research
    budget remains — address the remaining items or note them as open questions first.
    """
    desk = _desk(tool_context)
    state = tool_context.state
    # Mechanical closing contract: a desk that filed dispositions for less than
    # half its worklist, with budget still in hand, is quitting early — a failure
    # mode the eval kept catching. Enforce it here, not in prose. Two refusals
    # max: after that, close (the LoopAgent iteration cap is the hard stop).
    refusals = int(state.get(f"done_refusals:{desk}", 0))
    tri = state.get("triage") or {}
    if hasattr(tri, "model_dump"):
        tri = tri.model_dump()
    worklist = tri.get(desk) or []
    budget_left = int(state.get(f"research_budget:{desk}", 0))
    dispositions = len(state.get(f"flags:{desk}", []) or []) + len(
        state.get(f"open_questions:{desk}", []) or []
    )
    underworked = worklist and dispositions < _DONE_COVERAGE * len(worklist)
    if underworked and budget_left >= _DONE_MIN_BUDGET and refusals < _DONE_MAX_REFUSALS:
        state[f"done_refusals:{desk}"] = refusals + 1
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
    fetch_page,
    deep_research,
    query_precedent,
    file_rating_prediction,
    file_flag,
    note_open_question,
    done,
]

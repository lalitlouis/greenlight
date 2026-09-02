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
import contextlib
import difflib
import hashlib
import logging
import os
import re
import threading
import time
from typing import Any
from urllib.parse import urlparse

from google.adk.tools import ToolContext

from greenlight.contracts import ContractViolation, validate

DESKS = ("clearance_counsel", "ratings_board", "safety_underwriter", "territory_censor")

# The four desks run concurrently under a ParallelAgent. Shared counters would race,
# so flag ids are partitioned per desk and research budgets are per-desk keys.
# Spaced 1000, not 100: the sequence is per-desk, shared by all four clearance
# batches plus retry and sweep, and it increments on every ATTEMPT including
# rejections. On an entity-dense script (batching exists because 100+ item
# worklists happen) clearance passed 99 easily and F(100+101) collided with
# ratings' F201 — two unrelated findings that dedupe-by-id would then merge.
FLAG_ID_OFFSET = {
    "clearance_counsel": 1000,
    "ratings_board": 2000,
    "safety_underwriter": 3000,
    "territory_censor": 4000,
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
    """The base desk name, its batch names, the collapse-retry instance, and
    the completeness sweeper."""
    return (
        [desk]
        + [f"{desk}__b{i}" for i in range(1, CLEARANCE_MAX_BATCHES + 1)]
        + [f"{desk}__retry", f"{desk}__sweep"]
    )


def _mark_work_item(tool_context: ToolContext, work_item_id: str) -> None:
    """Record a work-item disposition in the per-agent side channel. Flags
    cannot carry the id (frozen schema, additionalProperties:false), so this
    is the single accounting mechanism done() and the completeness gate read."""
    if work_item_id:
        _state_append(tool_context, f"wi_done:{_agent_key(tool_context)}", work_item_id)


def desk_work_items_done(state: Any, desk: str) -> set[str]:
    """Work-item ids dispositioned by this desk (own name, batches, sweeper) —
    plus the clearance sweeper's, which the completeness gate credits to any
    desk: an id names one specific desk question, so exact-id credit cannot
    reproduce the blanket-sweep failure."""
    out: set[str] = set()
    for name in batch_agent_names(desk):
        out.update(state.get(f"wi_done:{name}") or [])
    out.update(state.get("wi_done:clearance_counsel__sweep") or [])
    return out


_SWEEP_WI_PREFIX = {
    "clearance_counsel": "CC",
    "ratings_board": "RB",
    "safety_underwriter": "SU",
    "territory_censor": "TC",
}


def sweep_work_item_id(desk: str, entity_id: str) -> str:
    """Desk-scoped id for an entity handed to the completeness sweeper.

    The sweeper runs under one name for all four desks, so an entity_id alone
    cannot say WHICH desk's question its disposition answered. A desk-scoped id
    can, which is what makes crediting it across desks safe."""
    return f"SW-{_SWEEP_WI_PREFIX.get(desk, desk[:2].upper())}-{entity_id}"


def _mentions(surface: str, text: str) -> bool:
    """Whole-word containment — `"ford" in "cannot afford"` is not a mention."""
    return re.search(rf"(?<!\w){re.escape(surface)}(?!\w)", text) is not None


def unexamined_entities(state: Any) -> list[dict[str, Any]]:  # noqa: PLR0912 - three deliberate accounting sweeps
    """Worklist items their OWN desk never dispositioned, plus extracted
    entities on no worklist at all. Coverage is desk-scoped: safety clearing
    the Nighthawks print as "no physical hazard" is true, irrelevant, and
    does NOT answer clearance's copyright question — the first live
    validation showed a blanket-sweeping desk satisfying the completeness
    gate on items whose real question was never asked. The gate loops on
    this before verification; survivors render NOT EXAMINED, never clean."""
    tri = _triage_dict(state)
    per_desk: dict[str, tuple[set[str], list[str]]] = {}
    for d in DESKS:
        covered: set[str] = set()
        for f in desk_flags(state, d):
            if f.get("entity_id"):
                covered.add(f["entity_id"])
        for c in desk_cleared(state, d):
            if c.get("entity_id"):
                covered.add(c["entity_id"])
        oqs = [str(q).lower() for q in desk_open_questions(state, d)]
        per_desk[d] = (covered, oqs)
    surfaces = {
        e.get("entity_id"): e.get("surface", "")
        for e in tri.get("entities") or []
        if isinstance(e, dict)
    }
    scenes_of = {
        e.get("entity_id"): e.get("scene_ids") or []
        for e in tri.get("entities") or []
        if isinstance(e, dict)
    }

    def _desk_covered(desk: str, eid: str) -> bool:
        covered, oqs = per_desk[desk]
        if eid in covered:
            return True
        # The completeness sweeper is named clearance_counsel__sweep, so its
        # work is only in THIS desk's family when the desk IS clearance. For
        # ratings/safety/territory its dispositions were invisible: the item was
        # examined, re-swept every round, and still rendered NOT EXAMINED.
        # Credit it the way work items are already credited — by EXACT id, so a
        # blanket sweep still cannot answer a question it never asked.
        if sweep_work_item_id(desk, eid) in desk_work_items_done(state, desk):
            return True
        surf = (surfaces.get(eid) or "").lower()
        # word-boundary, not substring: "ford" inside "cannot afford" credited
        # entity Ford as covered, so short-surfaced entities could be skipped by
        # every desk, never swept, and never disclosed
        return bool(surf) and any(_mentions(surf, q) for q in oqs)

    missing: dict[str, dict[str, Any]] = {}
    assigned: set[str] = set()
    for d in DESKS:
        for it in tri.get(d) or []:
            if not isinstance(it, dict) or not it.get("entity_id"):
                continue
            eid = it["entity_id"]
            assigned.add(eid)
            if not _desk_covered(d, eid):
                entry = missing.setdefault(
                    eid,
                    {
                        "entity_id": eid,
                        "surface": surfaces.get(eid, it.get("surface", "")),
                        "scene_ids": scenes_of.get(eid, []),
                        "desks": [],
                    },
                )
                entry["desks"].append(d)
    # scene-level work items (entity_id ""): tracked by work_item_id — the
    # only identity they have. Undispositioned ones surface to the gate with
    # scene ids harvested from the note.
    for d in DESKS:
        wi_done = desk_work_items_done(state, d)
        for it in tri.get(d) or []:
            if not isinstance(it, dict) or it.get("entity_id"):
                continue
            wid = it.get("work_item_id")
            if not wid or wid in wi_done:
                continue
            note = str(it.get("note") or "")
            missing[wid] = {
                "entity_id": None,
                "work_item_id": wid,
                "surface": note[:80],
                "scene_ids": re.findall(r"S\d{3}", note),
                "desks": [d],
            }

    # entities on NO worklist (pre-floor legacy records): any desk's answer counts
    for eid, surf in surfaces.items():
        if not eid or eid in assigned or eid in missing:
            continue
        if not any(_desk_covered(d, eid) for d in DESKS):
            missing[eid] = {
                "entity_id": eid,
                "surface": surf,
                "scene_ids": scenes_of.get(eid, []),
                "desks": ["clearance_counsel"],
            }
    return list(missing.values())


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


def collapsed_desks(state: Any) -> list[str]:
    """Desks with a worklist and ZERO dispositions of their own (batches and
    retry count as own; the generalist sweeper does not). The territory desk
    once spent all eight iterations on read_scene and filed nothing — this is
    the signature the completeness gate retries the desk on."""
    tri = _triage_dict(state)
    out: list[str] = []
    for d in DESKS:
        if not (tri.get(d) or []):
            continue
        n = (
            len(desk_flags(state, d))
            + len(desk_open_questions(state, d))
            + len(desk_cleared_own(state, d))
        )
        if n == 0:
            out.append(d)
    return out


def desk_cleared_own(state: Any, desk: str) -> list[Any]:
    """The desk's own clearances, EXCLUDING the completeness sweeper's — the
    sweeper's shallow generalist conclusions once rendered as '[Clearance
    counsel]' territory law and reversed the real desk's prior analysis."""
    out: list[Any] = []
    for name in batch_agent_names(desk):
        if name.endswith("__sweep"):
            continue
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
    if name.endswith(("__sweep", "__retry")):
        if state.get(key) is None:
            # sweep/retry work is mostly record_clearance; research is the exception
            state[key] = 12
        return key
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

    client = parallel.Parallel(api_key=os.environ["PARALLEL_API_KEY"], timeout=120.0, max_retries=3)
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


async def research(  # noqa: PLR0915 - one linear cache/dedupe/live sequence
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
    # queries join the key: a desk retrying the same objective with sharper
    # retrieval strings must get a fresh search, not the old results (the
    # objective-only key was deliberate but hid every retry).
    q_sig = "|".join(sorted(str(q) for q in (queries or [])))
    q_hash = hashlib.sha1((objective + "|" + q_sig + modifiers).encode()).hexdigest()[:12]
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
    # Atomic read-modify-write: a desk's parallel research calls in one turn
    # once BOTH read budget=N and BOTH wrote N-1 — two API calls, one counted.
    with _BUDGET_LOCK:
        budget = int(tool_context.state.get(budget_key, 0))
        if budget > 0:
            tool_context.state[budget_key] = budget - 1
    if budget <= 0:
        return {
            "error": "research budget spent",
            "guidance": (
                "File flags you can already support with earlier results, record what "
                "you could not resolve with note_open_question, then call done()."
            ),
        }

    session_id = f"scriptrisk-{getattr(tool_context, 'invocation_id', '') or 'run'}"[:64]

    # In-flight dedupe: two branches missing on the same key at the same
    # moment once both paid for the identical live search. The second waits
    # briefly for the first, then reads the durable cache.
    with _INFLIGHT_LOCK:
        pending = _INFLIGHT.get(key)
        if pending is None:
            _INFLIGHT[key] = threading.Event()
    if pending is not None:
        await asyncio.to_thread(pending.wait, 150)
        stored2 = await asyncio.to_thread(
            _durable_cache_load, q_hash if not entity_id else f"{entity_id}-{q_hash}"
        )
        if stored2 is not None:
            with _BUDGET_LOCK:  # refund: this branch spent no API call
                tool_context.state[budget_key] = int(tool_context.state.get(budget_key, 0)) + 1
            tool_context.state[key] = {k: v for k, v in stored2.items() if not k.startswith("_")}
            _index_research_key(tool_context, key)
            _register_provenance(
                tool_context,
                [
                    x
                    for r in stored2["results"]
                    for x in [r.get("title", ""), *r.get("excerpts", [])]
                ],
            )
            return {
                "cached": True,
                "deduped_in_flight": True,
                "results": stored2["results"],
                "search_id": stored2["search_id"],
            }
        # first caller failed or never saved — fall through to our own call
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
        with _BUDGET_LOCK:
            tool_context.state[budget_key] = int(tool_context.state.get(budget_key, 0)) + 1
        with _INFLIGHT_LOCK:
            ev = _INFLIGHT.pop(key, None)
        if ev:
            ev.set()
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
    with _INFLIGHT_LOCK:
        ev = _INFLIGHT.pop(key, None)
    if ev:
        ev.set()  # release any branch waiting on this exact search
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

    client = parallel.Parallel(api_key=os.environ["PARALLEL_API_KEY"], timeout=120.0, max_retries=3)
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

    client = parallel.Parallel(api_key=os.environ["PARALLEL_API_KEY"], timeout=120.0, max_retries=3)
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
_BUDGET_LOCK = threading.Lock()
_INFLIGHT: dict[str, threading.Event] = {}
_INFLIGHT_LOCK = threading.Lock()

# (normalized, ORIGINAL) pairs. The original is kept because the repair path
# and the handback hand text back to be filed as a VERBATIM citation — storing
# only the normalized form meant every repaired excerpt shipped lowercased,
# punctuation-rewritten and truncated mid-word, under a schema that calls the
# field "Verbatim supporting text. No paraphrase."
_PROV_TEXTS: dict[str, list[tuple[str, str]]] = {}
_PROV_MAX_RUNS = 8


def _prov_bucket(tool_context: ToolContext) -> list[tuple[str, str]]:
    inv = str(getattr(tool_context, "invocation_id", "") or "run")
    if inv not in _PROV_TEXTS and len(_PROV_TEXTS) >= _PROV_MAX_RUNS:
        _PROV_TEXTS.pop(next(iter(_PROV_TEXTS)))  # drop the oldest run's registry
    return _PROV_TEXTS.setdefault(inv, [])


# The marginal sentences rating_boundary ACTUALLY emitted this run — the only
# texts that earn the derived-marginal authority tier. A title string the model
# writes must never mint authority: the gates run before excerpt repair, so a
# decorated excerpt could clear authority and then be repaired to different text
# after the gate had already passed. Typed registry, exact-match only.
_MARGINAL_TEXTS: dict[str, set[str]] = {}


def _marginal_bucket(tool_context: ToolContext) -> set[str]:
    inv = str(getattr(tool_context, "invocation_id", "") or "run")
    if inv not in _MARGINAL_TEXTS and len(_MARGINAL_TEXTS) >= _PROV_MAX_RUNS:
        _MARGINAL_TEXTS.pop(next(iter(_MARGINAL_TEXTS)))
    return _MARGINAL_TEXTS.setdefault(inv, set())


def _register_provenance(tool_context: ToolContext, texts: list[str]) -> None:
    bucket = _prov_bucket(tool_context)
    bucket.extend((_norm_for_match(x), x) for x in texts if x)
    # excerpts arrive as storage chunks; a desk quoting across a chunk boundary
    # is still verbatim — register the joined text as well
    joined = " ".join(x for x in texts if x)
    if joined:
        bucket.append((_norm_for_match(joined), joined))


def _register_tool_output(tool_context: ToolContext, obj: Any) -> None:
    """Register a local tool's returned content as citable provenance. The
    desks are instructed to cite these tools verbatim, but until this existed
    their output was absent from the registry — file_flag rejected the very
    citations the tools demand, or worse, the >=60%-overlap repair silently
    substituted some OTHER registered text. With the true text registered,
    exact quotes pass and near-miss repair resolves to the consulted source."""
    import json as _json

    texts: list[str] = []

    def _walk(v: Any) -> None:
        if isinstance(v, str):
            if v.strip():
                texts.append(v)
        elif isinstance(v, dict):
            for k, vv in v.items():
                texts.append(str(k))
                _walk(vv)
        elif isinstance(v, (list, tuple)):
            for vv in v:
                _walk(vv)

    _walk(obj)
    with contextlib.suppress(Exception):
        texts.append(_json.dumps(obj, ensure_ascii=False))
    _register_provenance(tool_context, texts)


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
# Order-preserving coverage of the needle by one source, anchored on a
# contiguous run. 0.70 keeps the legitimate case working (a desk that inserts
# "on screen" and "by them" into a real excerpt scores ~0.79 — the Winklevoss
# shape, where 33 straight rejections once burned a desk's whole tail), while
# ORDER plus the run anchor are what actually kill the substitution: unrelated
# text sharing the same legal vocabulary scrambles to ~0.4 and has no 5-word
# run in common. The ratio tunes leniency; ordering provides the safety.
_REPAIR_RATIO = 0.70
_REPAIR_MIN_RUN = 5
_HANDBACK_RATIO = 0.25
_REPAIR_MAX_EXTRA = 3.0  # a repair may not balloon the quote beyond this factor


def _overlap_ratio(needle: str, candidate: str) -> float:
    """Share of the needle's substantive words present in the candidate.
    Order-INSENSITIVE — only for ranking handback suggestions, never for
    deciding that a citation may be rewritten."""
    min_word_len = 3
    words = [w for w in _norm_for_match(needle).split() if len(w) >= min_word_len]
    if len(words) < _REPAIR_MIN_WORDS:
        return 0.0
    need = set(words)
    cand = set(_norm_for_match(candidate).split())
    return len(need & cand) / len(need)


_ALIGN_STRIP = ".,;:!?\"'()[]{}<>-" + "\u2013\u2014\u2026"


def _align_tokens(s: str) -> list[str]:
    return [w.strip(_ALIGN_STRIP) for w in s.split()]


def _aligned_span(needle: str, cand_norm: str, cand_orig: str) -> tuple[float, int, str]:
    """Align the needle against one registered text IN ORDER.

    Returns (coverage, longest contiguous run, the aligned span of the ORIGINAL
    text). Coverage is the order-preserving share of the needle's words the
    candidate reproduces, so shared vocabulary in a different order no longer
    counts as a match — which is what let an unrelated source, or the joined
    blob of every excerpt from one search, score 1.0 on a set-intersection.
    """
    # strip punctuation for ALIGNMENT only: "light," and "light" are the same
    # word, and treating them as different broke every block at a comma. Token
    # count is preserved, so indices still map back to the original words.
    nw = _align_tokens(_norm_for_match(needle))
    cw = _align_tokens(cand_norm)
    ow = cand_orig.split()
    if len(nw) < _REPAIR_MIN_WORDS or not cw:
        return 0.0, 0, ""
    blocks = difflib.SequenceMatcher(None, nw, cw, autojunk=False).get_matching_blocks()
    real = [b for b in blocks if b.size]
    if not real:
        return 0.0, 0, ""
    matched = sum(b.size for b in real)
    longest = max(b.size for b in real)
    # the candidate's own words spanning the aligned region — NOT its first N
    # characters, which is how a repair used to file the opening of an
    # unrelated excerpt as the quote
    start, end = real[0].b, real[-1].b + real[-1].size
    span = " ".join(ow[start:end]) if len(ow) == len(cw) else cand_orig[:800]
    return matched / len(nw), longest, span


def _best_registry_match(attempt: str, tool_context: ToolContext) -> str | None:
    """The registered text the model was clearly reaching for, if any.

    A repair REWRITES a citation the report will present as verbatim, so the bar
    is deliberately high: the candidate must reproduce >=85% of the attempted
    quote's words IN ORDER, anchored on a contiguous run of >=5, and the span it
    hands back may not balloon the quote. That is the signature of a real
    retrieval the model transcribed loosely (markdown stripped, a word dropped).
    The old test — 60% of the words in any order — matched on shared legal
    vocabulary alone, so an unrelated source could be substituted and filed as
    the verbatim citation.
    """
    best_span, best_r = None, 0.0
    for norm, orig in _prov_bucket(tool_context):
        r, longest, span = _aligned_span(attempt, norm, orig)
        if r < _REPAIR_RATIO or longest < _REPAIR_MIN_RUN or not span:
            continue
        if len(span.split()) > _REPAIR_MAX_EXTRA * max(1, len(attempt.split())):
            continue
        if r > best_r:
            best_span, best_r = span, r
    return best_span[:800] if best_span else None


def _handback_candidates(attempts: list[str], tool_context: ToolContext) -> list[str]:
    """Closest registered texts to the failed quotes — race-free, from the
    process registry — offered back in the rejection for verbatim copying.
    Ranking may be loose here: the MODEL copies from these, nothing is
    rewritten on its behalf."""
    scored: list[tuple[float, str]] = []
    for norm, orig in _prov_bucket(tool_context):
        r = max((_overlap_ratio(a, norm) for a in attempts), default=0.0)
        if r >= _HANDBACK_RATIO:
            scored.append((r, orig))
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


# run-13 item 3: which descriptor family answers for each rating category —
# the structured marginal attaches by the FLAG's category, most specific
# descriptor first, from the desk's last rating_boundary call.
_CATEGORY_FAMILY = {
    "rating_language": "language",
    "rating_violence": "violence",
    "rating_drug_use": "drugs",
    "rating_alcohol": "alcohol",
    "rating_sexuality": "sexual_content",
    "rating_thematic_elements": "thematic",
}
# The hedge that substituted for the number in runs 10-12. Allowed only when
# the structured marginal is attached (then it summarizes a shown figure).
_MARGINAL_HEDGE_RE = re.compile(r"\bpatterns\s+(?:strongly\s+)?(?:toward|across)\b", re.IGNORECASE)


def _attach_marginal(tool_context: ToolContext, category: str) -> dict[str, Any] | None:
    """The structured marginal for this flag's category family, from the desk's
    last rating_boundary call — deterministic, never model-supplied. Most
    specific descriptor wins ('pervasive language' over 'language'); None when
    the family had no match (the render hard gate makes that visible)."""
    fam = _CATEGORY_FAMILY.get(category)
    if not fam:
        return None
    last = tool_context.state.get(f"marginal_last:{_agent_key(tool_context)}") or {}
    candidates = [k for k in last if k == fam or k.endswith(" " + fam)]
    if not candidates:
        return None
    best = max(candidates, key=len)  # intensity-qualified beats bare
    return dict(last[best])


def _rating_marginal_gate(
    tool_context: ToolContext, category: str, finding: str, flag: dict[str, Any]
) -> str | None:
    """run-13 item 3: attach the structured marginal from the desk's last
    rating_boundary call (tool-supplied, never model-typed); reject the hedge
    that substituted for the missing number in runs 10-12."""
    if not category.startswith("rating_"):
        return None
    marginal = _attach_marginal(tool_context, category)
    if marginal:
        flag["marginal"] = marginal
        return None
    if _MARGINAL_HEDGE_RE.search(finding):
        return (
            "REJECTED, not filed: the finding hedges ('patterns toward') with no "
            "measured marginal behind it. Call rating_boundary with the descriptors "
            "you counted FIRST — the marginal attaches to the flag automatically — "
            "then refile. A rating finding without its marginal will not render."
        )
    return None


# run-15: the sync/master cost model kept flip-flopping (run 14 split Baba
# O'Riley into two findings; run 15 bundled both rights into one) — a different
# model each run moves the headline number on an unchanged script. Doctrine is
# settled: composition and master are separately owned and separately priced,
# so they file as TWO findings, always.
def _sync_master_split_problem(category: str, finding: str, remedy_detail: str) -> str | None:
    if "sync" not in (category or ""):
        return None
    blob = f"{finding} {remedy_detail}".lower()
    if "master use license" in blob or "master-use license" in blob:
        return (
            "REJECTED, not filed: this sync finding bundles the master-use claim. "
            "Composition and master are SEPARATELY OWNED rights with separate "
            "licensors and separate fees — file this finding for the composition "
            "sync license ONLY (drop the master clause), then file a second "
            "finding with category master_use_license for the recording. One "
            "flag per right keeps the cost roll-up stable run to run."
        )
    return None


def _manifest_note(tool_context: ToolContext, entry: dict[str, Any]) -> None:
    """Append one guard-fire entry under this agent's own manifest key (per-agent
    keys — the batch-agent state rule). Pipeline unions all keys into
    record['guard_manifest']."""
    key = f"guard_manifest:{_agent_key(tool_context)}"
    entries = list(tool_context.state.get(key) or [])
    entries.append(entry)
    tool_context.state[key] = entries


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
    norms = [n for n, _ in bucket]
    for text in norms:
        if needle in text:
            return True
    if _word_overlap_hit(needle, norms):
        return True
    if os.getenv("GREENLIGHT_PROV_DEBUG"):
        with open("/tmp/prov_debug.jsonl", "a") as fh:
            import json as _json

            fh.write(_json.dumps({"needle": needle[:400], "bucket_n": len(bucket)}) + "\n")
    return _exists_in_state(needle, tool_context.state)


def _exists_in_state(needle: str, state: Any) -> bool:
    """Secondary provenance sources kept in session state: the script itself,
    per-desk research indices, and precedent rationales."""
    # "source" is a key NOTHING writes — the pipeline seeds the screenplay as
    # script_text. This leg was dead, so a desk quoting the screenplay verbatim
    # (which file_flag's own rejection message names as legitimate) always
    # failed provenance and fell through to the repair path, where an unrelated
    # research excerpt could be substituted for the script quote.
    script = state.get("script_text") or state.get("source") or ""
    if needle in _norm_for_match(script):
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
    "bhroberts.org",
    "grokipedia.com",
    "whoppah.com",
    "go-legal.ai",
    "cinemacafe.com",
    "uscspotlight.com",
    "jakedavidowitz.com",
    "enduser-medianetworksproductionsafety-prod.paramount.com",
    "yelp.com",
    "trademarkia.com",
    "filmindependent.org",
    # run-7: cited as authority for a Lanham Act / classification claim
    "substack.com",  # a newsletter is not legal authority (fictionistas.substack)
    "songmeanings.com",  # crowd lyrics annotations, not publishing administration
    # run-8: blogs and gateways cited for CARA / BBFC / child-labor / NIN splits
    "wordpress.com",  # pekoeblaze.wordpress.com for BBFC classification
    "bandcamp.com",  # natesu.bandcamp.com for NIN publishing administration
    "ipfs.io",  # a content-gateway URL that may not resolve next week
    # run-9: weak sources cited for venue / CARA / stunt / territory claims
    "bayut.com",  # UAE property listings, cited for UAE media content standards
    "squarespace.com",  # bare CDN / squarespace-hosted page (static1.squarespace.com)
    "ginflatables.com",  # inflatables vendor, cited for stunt-water safety
    "digitalcommons.georgiasouthern.edu",  # student thesis repo, cited for CARA
    "fsufilmhandbook.com",  # student film handbook, cited for stunt safety
    # run-10: a HIGH SCHOOL newspaper survived verification as CARA authority —
    # worse than the municipal .gov it slipped past. Plus local news and a blog
    # cited as authority for venues and a Ninth Circuit trademark case.
    "whstheshield.com",  # high school student newspaper, cited for CARA alcohol
    "thoolie.com",  # cited as authority for Body English / Tao nightclubs
    "ksl.com",  # Utah local news, cited for the Pure nightclub
    "turtletalk.blog",  # a federal-Indian-law blog cited for a 9th Cir. trademark case
    # run-12: operating-status claims — the report's highest-risk facts — resting
    # on a directions site and a blog as sole sources
    "mapquest.com",
    "blogspot.com",
    # run-14: F1016 rendered ELEVEN citations — a social post and nightlife
    # listicles piled beside the Clark County authority
    "x.com",
    "twitter.com",
    "1800lasvegas.com",
    "nocovernightclubs.com",
    "thelifeofluxury.com",
    "las-vegas-theater.com",
    "seeing-stars.com",
    "uniquevenues.com",
}

_SCENE_ANCHOR_CAP = 8  # a finding spanning more scenes than this says "the script"


def state_get_list(tool_context: ToolContext, prefix: str) -> list[str]:
    out: list[str] = []
    desk = _desk(tool_context)
    for name in batch_agent_names(desk):
        out.extend(tool_context.state.get(f"{prefix}:{name}") or [])
    return out


def _is_background_host(url: str) -> bool:
    if "wikipedia_en_all" in (url or "") or "/kiwix" in (url or ""):
        return True  # offline Wikipedia dumps on personal domains ARE Wikipedia
    seg = (url or "").split("/")[2:3]
    if not seg:
        return True
    host = seg[0].removeprefix("www.")
    root = ".".join(host.split(".")[-2:])
    return host in BACKGROUND_HOSTS or root in BACKGROUND_HOSTS


# The authority allowlist — the one structural item open since run 2. The
# background list is default-ALLOW (an unknown personal domain counts as
# non-background), which is how a BLOCKER shipped on a Kiwix Wikipedia dump at
# a.osmarks.net. Top severities are default-DENY: they need a source from here.
AUTHORITY_HOSTS = {
    # ratings / classification bodies
    "filmratings.com",
    "motionpictures.org",
    "bbfc.co.uk",
    # safety
    "csatf.org",
    "contractservices.org",
    # registries / law — federal agencies must be named (structure alone can't
    # tell uspto.gov from highpointnc.gov). Add a federal .gov here as it proves
    # legitimate rather than trusting every "gov" label.
    "copyright.gov",
    "uspto.gov",
    "osha.gov",
    "sec.gov",
    "ftc.gov",
    "dol.gov",
    "wipo.int",
    "law.cornell.edu",
    "courtlistener.com",
    "justia.com",
    # foreign national governments as FULL HOSTS — never the bare "gov.uk"
    # suffix, which root-matches every council (belfastcity.gov.uk)
    "legislation.gov.uk",
    "uaelegislation.gov.ae",
    # location / permit authorities (venue findings) — named exceptions to the
    # municipal-.gov ban: a county film office IS the filming authority for its
    # jurisdiction. Clark County is the Las Vegas permitting authority; banning
    # every county .gov (run 9) took the actual venue authority with it.
    "clarkcountynv.gov",
    "filmla.com",
    "lvmpd.com",
    # music rights
    "ascap.com",
    "bmi.com",
    "sesac.com",
    "harryfox.com",
    # major trades (industry-practice claims)
    "variety.com",
    "hollywoodreporter.com",
    "deadline.com",
    "billboard.com",
}


def _host_root(url: str) -> str:
    seg = (url or "").split("/")[2:3]
    if not seg:
        return ""
    host = seg[0].removeprefix("www.")
    root = ".".join(host.split(".")[-2:])
    return host if host in AUTHORITY_HOSTS | RATING_AUTHORITY_HOSTS else root


# US state second-level .gov domains (dir.ca.gov, film.nv.gov are real
# authorities). Municipal .gov domains — highpointnc.gov, belfastcity.gov.uk —
# are NOT: a city site is not the CARA/BBFC/federal authority, and "any label
# 'gov' = authority" waved four highpointnc.gov cites for CARA standards
# straight through (run 8).
_US_STATES = frozenset(
    [
        "al",
        "ak",
        "az",
        "ar",
        "ca",
        "co",
        "ct",
        "de",
        "fl",
        "ga",
        "hi",
        "id",
        "il",
        "in",
        "ia",
        "ks",
        "ky",
        "la",
        "me",
        "md",
        "ma",
        "mi",
        "mn",
        "ms",
        "mo",
        "mt",
        "ne",
        "nv",
        "nh",
        "nj",
        "nm",
        "ny",
        "nc",
        "nd",
        "oh",
        "ok",
        "or",
        "pa",
        "ri",
        "sc",
        "sd",
        "tn",
        "tx",
        "ut",
        "vt",
        "va",
        "wa",
        "wv",
        "wi",
        "wy",
        "dc",
    ]
)
# bare national government sites, matched by EXACT host only (never as a root
# suffix, which would sweep in every council under gov.uk / gov.ae)
_NATIONAL_GOV_EXACT = frozenset({"gov.uk", "www.gov.uk", "gov.cn", "www.gov.cn"})


def _is_authority_host(url: str) -> bool:
    seg = (url or "").split("/")[2:3]
    if not seg:
        return False
    host = seg[0].removeprefix("www.")
    root = ".".join(host.split(".")[-2:])
    if host in AUTHORITY_HOSTS or root in AUTHORITY_HOSTS:
        return True
    parts = host.split(".")
    if host.endswith(".int") or host in _NATIONAL_GOV_EXACT:
        return True
    # US STATE domains only (xx.gov / dir.ca.gov). Everything else with a "gov"
    # label — federal agencies AND foreign national governments — must be on the
    # allowlist BY NAME. That is deliberate: it is the only way to keep a
    # municipal .gov / council .gov.uk OUT (highpointnc.gov, belfastcity.gov.uk)
    # while letting uspto.gov and gov.uk in, since the two are structurally
    # identical and cannot be told apart by shape.
    if "gov" in parts:
        gi = parts.index("gov")
        return gi >= 1 and parts[gi - 1] in _US_STATES
    return False


# A ratings claim needs a ratings authority — being government is not enough.
# Run 6 cited committee.nottinghamcity.gov.uk (a city council) for BBFC
# classification guidelines; run 5 cited Belfast council minutes. Same class.
RATING_AUTHORITY_HOSTS = {
    "filmratings.com",
    "motionpictures.org",
    "bbfc.co.uk",
    "variety.com",
    "hollywoodreporter.com",
    "deadline.com",
}


def _authority_problem(
    severity: str,
    cits: list[dict[str, Any]],
    category: str = "",
    tool_context: ToolContext | None = None,
) -> str | None:
    """Default-deny sourcing for the report's loudest claims. A BLOCKER needs
    at least one allowlisted authority; a HIGH needs an authority OR two
    distinct non-background hosts corroborating each other. Rating categories
    are stricter: only ratings bodies and major trades qualify — a random
    .gov domain is not an authority on CARA or the BBFC."""
    if severity not in ("BLOCKER", "HIGH"):
        return None
    urls = [c.get("url") or "" for c in cits]
    if category.startswith("rating_"):
        if any(_host_root(u) in RATING_AUTHORITY_HOSTS for u in urls) or any(
            _is_derived_marginal(c, tool_context) for c in cits
        ):
            return None
        hosts = ", ".join(sorted({(u.split("/")[2:3] or ["?"])[0] for u in urls})) or "none"
        return (
            f"REJECTED, not filed: a {severity} ratings finding must cite a ratings "
            "authority (filmratings.com, motionpictures.org, BBFC) or a major trade "
            f"(Variety, THR, Deadline). Current hosts: {hosts} — a government domain "
            "that is not the classification body itself does not qualify. Re-run "
            "research() with restrict_to_domains on those hosts, or file at MEDIUM."
        )
    if any(_is_authority_host(u) for u in urls):
        return None
    _host_idx = 2  # scheme://host/...
    distinct = {
        u.split("/")[_host_idx].removeprefix("www.")
        for u in urls
        if not _is_background_host(u) and len(u.split("/")) > _host_idx
    }
    corroborated = 2  # two independent non-background sources
    if severity == "HIGH" and len(distinct) >= corroborated:
        return None
    hosts = ", ".join(sorted({(u.split("/")[2:3] or ["?"])[0] for u in urls})) or "none"
    return (
        f"REJECTED, not filed: a {severity} finding must rest on at least one "
        "ALLOWLISTED authority (regulator, government/court, rights registry, "
        "CSATF, CARA/filmratings.com, BBFC, or a major trade)"
        + ("" if severity == "BLOCKER" else " — or two independent non-background sources")
        + f". Current hosts: {hosts}. Re-run research() targeting an authority "
        "for this claim's domain, or file at the severity your sourcing carries."
    )


_URL_HOST_IDX = 2  # "scheme:", "", "host", "rest" after split("/", 3)
_URL_PATH_IDX = 3


def _cit_key(url: str) -> str:
    """host+path, scheme- and subdomain-insensitive (www./m. stripped), trailing
    slash stripped — so 'csatf.org', 'www.csatf.org' and 'm.csatf.org' are ONE
    citation, not three (run 8: www; run 9: m.yelp.com beside yelp.com)."""
    parts = (url or "").split("/", 3)
    if len(parts) > _URL_HOST_IDX:
        host = parts[_URL_HOST_IDX].lower().removeprefix("www.").removeprefix("m.")
    else:
        host = (url or "").lower()
    path = ("/" + parts[_URL_PATH_IDX]).rstrip("/") if len(parts) > _URL_PATH_IDX else ""
    return host + path


def _dedupe_cits(cits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for c in cits:
        k = _cit_key(c.get("url") or "") or (c.get("excerpt") or "")[:60]
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


def _is_derived_marginal(c: dict[str, Any], tool_context: ToolContext | None = None) -> bool:
    """Our own rating_boundary marginal — a URL-less tool citation, and the desk's
    strongest, most specific rating evidence. It must count as authority, or the
    prune below drops it (no URL) for a generic filmratings.com page and the
    measured 4,544-rationale marginal never renders. TYPED, not title-matched:
    only an excerpt rating_boundary actually emitted this run qualifies — a title
    string the model writes cannot mint authority. Without a tool_context there is
    no registry, so the answer is no."""
    if tool_context is None:
        return False
    return _norm_for_match(c.get("excerpt") or "") in _marginal_bucket(tool_context)


def _prune_weak_citations(
    cits: list[dict[str, Any]], category: str, tool_context: ToolContext | None = None
) -> list[dict[str, Any]]:
    """When a finding already has a strong source, the weak ones must not render
    beside it — a CARA claim citing filmratings AND highpointnc.gov reads as
    carelessness (run 8: the municipal site appeared four times). Never empties
    the list; the citation invariant still holds."""
    if len(cits) <= 1:
        return _dedupe_cits(cits)
    urls = [c.get("url") or "" for c in cits]
    if category.startswith("rating_"):
        strong = [
            c
            for c, u in zip(cits, urls, strict=False)
            if _host_root(u) in RATING_AUTHORITY_HOSTS or _is_derived_marginal(c, tool_context)
        ]
        if strong:
            return _dedupe_cits(strong)
    keep = [
        c
        for c, u in zip(cits, urls, strict=False)
        # a URL-less citation reads as background by default, which pruned first
        # the derived marginal (run 11) and then the auto-attached statute span
        # (gate #14) — verbatim provisions and our own tool citations are never
        # the weak ones
        if not _is_background_host(u)
        or c.get("source_type") == "statute"
        or _is_derived_marginal(c, tool_context)
    ]
    return _dedupe_cits(keep or cits)


def _background_only_problem(
    severity: str, cits: list[dict[str, Any]], tool_context: ToolContext | None = None
) -> str | None:
    """A legal conclusion needs at least one non-background source. Fan wikis
    and forums may inform, but they cannot carry a MEDIUM+ finding alone."""
    if severity not in ("BLOCKER", "HIGH", "MEDIUM"):
        return None
    # The derived rating_boundary marginal has no URL but is authoritative — a
    # rating finding citing only the corpus must not read as background-only.
    if not all(
        _is_background_host(c.get("url") or "") and not _is_derived_marginal(c, tool_context)
        for c in cits
    ):
        return None
    return (
        "REJECTED, not filed: every citation is a background-tier source (fan "
        "wiki, forum, general-interest site). A finding at this severity needs "
        "at least one authoritative source — regulator or government site, "
        "USPTO/Copyright Office, CSATF, CARA/filmratings.com, BBFC, primary "
        "statutes, or law-firm analysis. Re-run research() with "
        "restrict_to_domains targeting those, or lower the severity to LOW/FYI "
        "if the claim only merits background support."
    )


# Rule-shaped rating claims, deterministically. Run 10 rejected them (marginal
# attached to a rule it cannot support); the run-11 prompt fix taught the desk to
# stop attaching the marginal while KEEPING the rule — the verifier went quiet and
# the desk got worse ("this census profile directly commands an R rating" survived
# as PARTIAL). A prompt cannot hold this line; a filing gate can: no descriptor
# table contains a rule, so a rating finding may only assert the observation.
_NORMATIVE_RULE_RE = re.compile(
    r"(?:directly\s+)?\b(?:commands?|mandates?|forces?|guarantees?|compels?)\s+"
    r"(?:a|an|the)?\s*(?:G|PG|PG-13|R|NC-17)\b"
    r"|\brequires?\s+(?:a|an|the)?\s*(?:G|PG|PG-13|R|NC-17)\s+rating"
    r"|\bCARA\s+(?:rules?|guidelines?|standards?)\s+"
    r"(?:require|restrict|mandate|prohibit|forbid|limit)"
    r"|\bautomatic(?:ally)?\s+(?:triggers?|draws?|results?|receives?|earns?)"
    r"|\btriggers?\s+(?:a|an)\s+(?:R|NC-17)\s+rating"
    r"|\bexceeds?\s+PG-13\s+tolerances\b"
    r"|\bunder\s+CARA\s+standards?,?\s+\w[^.]{0,60}?\brequires?\b"
    # run-13: the phrase class the run-12 list missed — every pattern anchored
    # to a rating token, so "within swimwear coverage" (a real wardrobe remedy)
    # passes while "within PG-13 parameters" is caught.
    r"|\bconform(?:s|ing)?\s+to\s+(?:the\s+)?(?:G|PG|PG-13|R|NC-17)\b"
    r"|\bwithin\s+(?:the\s+)?(?:G|PG|PG-13|R|NC-17)(?:-band)?"
    r"[\w\s,-]{0,40}?(?:parameters?|limits?|tolerances?|boundar(?:y|ies)|guidelines?)"
    r"|\bmaintain\s+(?:alignment|compliance)\s+with\s+(?:the\s+)?(?:G|PG|PG-13|R|NC-17)\b"
    r"|\bretain(?:ing)?\s+(?:at\s+most|no\s+more\s+than)\s+\d",
    re.IGNORECASE,
)


def _normative_rule_problem(category: str, finding: str, remedy_detail: str) -> str | None:
    """A rating finding may not assert a normative CARA rule — the corpus measures
    what CARA DID, not what it requires, so a rule claim is unverifiable by
    construction and poisons the marginal cited beside it."""
    if not category.startswith("rating_"):
        return None
    hit = _NORMATIVE_RULE_RE.search(finding or "") or _NORMATIVE_RULE_RE.search(remedy_detail or "")
    if not hit:
        return None
    return (
        f'REJECTED, not filed: the text asserts a normative CARA rule ("{hit.group(0)}"). '
        "No descriptor table contains a rule — a distribution says what CARA did, not what "
        "it requires — so the verifier cannot support this claim shape. Restate as the "
        "OBSERVATION: the counted content matches CARA descriptor 'X', which patterns "
        "toward <band> in the descriptor corpus (cite the rating_boundary marginal), and "
        "frame the band as measured boundary risk, never an automatic outcome."
    )


def _umbrella_problem(category: str, scene_ids: list[str]) -> str | None:
    """One finding per entity, anchored where the issue occurs. Ratings and
    territory findings legitimately aggregate cumulative content; everything
    else spanning the whole script is an umbrella flag that swallows real
    entities (the F101 failure: 137 scenes, twelve people, one finding)."""
    if category.startswith(("rating_", "territory_")) or len(scene_ids) <= _SCENE_ANCHOR_CAP:
        return None
    return (
        f"REJECTED, not filed: this finding anchors to {len(scene_ids)} scenes. "
        f"Anchor to the {_SCENE_ANCHOR_CAP} scenes where the issue is strongest. "
        "If several distinct entities share this issue, file ONE FINDING PER "
        "ENTITY — each named person, brand, or work gets its own finding with "
        "its own citations and remedy."
    )


def _unverified_regs(tool_context: ToolContext, finding: str) -> str | None:
    """A cited registration number must resolve on the register — an invented
    one would look identically authoritative (review item #8)."""
    cited = re.findall(r"[Rr]eg(?:istration)?\.?\s*#?\s*([0-9]{6,8})", finding)
    if not cited:
        return None
    verified = set(state_get_list(tool_context, "verified_marks"))
    unverified = [n for n in cited if n not in verified]
    if not unverified:
        return None
    return (
        f"REJECTED, not filed: registration number(s) {unverified} are cited but were "
        "not verified this run. Call verify_trademark() first; if it cannot resolve "
        "the number, describe the mark WITHOUT a number."
    )


# run-15 follow-up (the reviewer's named class): uncited PRECISION. A statute
# section typed from memory looks identically authoritative to a retrieved one —
# and the child-labor hour caps drifted between runs (3h/4.5h vs 4h/2h) because
# nothing tied them to a source. A precise premise figure must trace to a
# retrieved text or it does not file.
_STATUTE_CITE_RE = re.compile(
    r"\b(?:\d+\s+)?(?:CFR|C\.F\.R\.|NRS|CCR|USC|U\.S\.C\.)\s*(?:§+\s*)?(?:Chapter\s+)?([\d.]+)"
    r"|\bLabor\s+Code\b[^.;]{0,20}?§*\s*([\d.]+)"
    r"|§+\s*([\d.]+)",
    re.IGNORECASE,
)
_MIN_SECTION_DIGITS = 3  # '29 CFR 1910.28' -> gate on 1910, never on the title 29
# hour caps gate ONLY in minor-safety findings — the known drift class. A stunt
# finding's '4 hours of rehearsal' is planning prose, not a statutory limit
# (anti-oscillation: named negative control, pinned in tests).
_HOURS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*hours?\b", re.IGNORECASE)


def _statute_sections(text: str) -> set[str]:
    out: set[str] = set()
    for m in _STATUTE_CITE_RE.finditer(text or ""):
        num = next((g for g in m.groups() if g), "")
        whole = num.split(".")[0]
        if len(whole) >= _MIN_SECTION_DIGITS:
            out.add(whole)
    return out


_CITE_WINDOW = 170  # chars either side of the section number in the source


def _uncited_statute_problem(
    tool_context: ToolContext,
    category: str,
    finding: str,
    remedy_detail: str,
    cits: list[dict[str, Any]] | None = None,
) -> str | None:
    """Every statute section (and, in minor-safety findings, every hour cap)
    must appear in a text this run actually retrieved. Typed-from-memory
    precision is the fabrication class wearing a suit.

    Reader-traceability repair (gate #13): a desk that quotes a statute's
    OPERATIVE sentences — good excerpt discipline — while the section number
    sits elsewhere in the retrieved text is not punished with a refile; the
    verbatim span AROUND the number is auto-attached as an extra citation, so
    the reader can verify the cite from the excerpt beside it."""
    body = f"{finding} {remedy_detail}"
    needed = _statute_sections(body)
    if (category or "").startswith("minor"):
        needed |= {m.group(1) for m in _HOURS_RE.finditer(body)}
    if not needed:
        return None
    excerpts = " ".join(str(c.get("excerpt") or "") for c in (cits or []))
    prov_pairs = _prov_bucket(tool_context)
    prov = " ".join(norm for norm, _ in prov_pairs)
    missing = []
    for n in sorted(needed):
        if n in excerpts:
            continue  # already reader-traceable
        if n not in prov:
            missing.append(n)
            continue
        if cits is None or len(n) < _MIN_SECTION_DIGITS:
            continue  # hour caps: retrieved is enough; no auto-attach for 1-digit numbers
        src = next((orig for _, orig in prov_pairs if n in orig), None)
        if src:
            i = src.index(n)
            span = src[max(0, i - _CITE_WINDOW) : i + _CITE_WINDOW]
            span = span[span.find(" ") + 1 : span.rfind(" ")] if " " in span else span
            cits.append(
                {
                    "source_type": "statute",
                    "title": "cited provision (auto-attached for traceability)",
                    "url": None,
                    "excerpt": span.strip(),
                    "retrieved_at": None,
                    "via": "local",
                    "repaired": True,
                }
            )
            _manifest_note(
                tool_context,
                {"guard": "statute_cite_attached", "stage": "filing", "matched": n},
            )
    if not missing:
        return None
    return (
        f"REJECTED, not filed: the figure(s) {missing} (statute section or statutory "
        "limit) appear in NO source retrieved this run — a precise number typed from "
        "memory reads as authoritative and cannot be verified. research() the actual "
        "provision (restrict_to_domains law.cornell.edu, govinfo.gov, dir.ca.gov, "
        "leg.state.nv.us) and QUOTE the text that states it, or state the obligation "
        "without the number."
    )


def _clip_words(text: str, limit: int) -> str:
    """Cap at a word boundary — a mid-word slice reads as a data bug."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:—-") + " …"


def _strip_json_escapes(text: str) -> str:
    """Model output occasionally leaks JSON-style escapes into free text
    (He\\'ll, \\"quote\\"); rendered verbatim the backslash shows. Strip only
    backslash-before-quote — never touch legitimate backslashes."""
    return re.sub(r"\\+([\"'])", r"\1", text or "")


def file_flag(  # noqa: PLR0912, PLR0915 - a deliberate sequence of filing gates
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
    work_item_id: str = "",
) -> str:
    """File one finding. A flag without a citation is REJECTED — this is enforced.

    scene_ids: ONLY the scenes where the element itself appears on the page,
      e.g. ["S004"] — never "the sequence around it"; a scene chip pointing at
      text that lacks the element reads as fabrication to the reader.
    severity: BLOCKER | HIGH | MEDIUM | LOW | FYI — a RISK judgment; use the FULL scale.
      BLOCKER: stops photography or makes the film UNDELIVERABLE IN ITS PRIMARY
      market. A market-specific alternate-cut requirement (a CN or UAE localized
      delivery cut priced in four figures) is HIGH with a deliverables note, never
      a BLOCKER — "do not shoot as written" must be literally true. HIGH: large exposure or an
      expensive remedy (five figures up, or real schedule impact). MEDIUM: real cost or
      negotiation, but bounded and routine. LOW: cheap, local fix — a dialogue swap, a
      prop rename, a set-dressing change. FYI: no action required; filed for awareness
      (usually NO_ACTION). A report where everything sits at MEDIUM+ cannot be triaged:
      if the remedy is a free line change, the severity is LOW, not MEDIUM.
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
    work_item_id: the worklist item this dispositions (e.g. "TC-W003") — pass it
      whenever your worklist item shows one; it is how the closing gate sees
      scene-level work that has no entity_id.

    On rejection you get every validation error at once — fix them all and refile once.
    """
    desk = _desk(tool_context)
    seq = _next_flag_seq(tool_context, desk)

    cits = []
    for c in citations:
        cit = {
            "source_type": c.get("source_type", "web"),
            "title": _strip_json_escapes(c.get("title", "")),
            "url": c.get("url"),
            "excerpt": _strip_json_escapes(c.get("excerpt", "")),
            "retrieved_at": None,
            "via": c.get("via", "parallel_search"),
        }
        if _is_derived_marginal(cit, tool_context):
            # The desk files the corpus marginal under whatever url/via it last
            # researched (run 12: url=filmratings.com, via=parallel_search), so our
            # own aggregate rendered as filmratings' — misattribution both ways.
            # Normalize: the marginal is a local tool citation, named as ours.
            cit["url"] = None
            cit["via"] = "local"  # schema enum; the title carries the attribution
            cit["source_type"] = "rules_table"
            cit["title"] = "ScriptRisk CARA descriptor corpus (4,544 official rationales)"
        cits.append(cit)

    flag: dict[str, Any] = {
        "flag_id": f"F{FLAG_ID_OFFSET[desk] + seq}",
        "agent": desk,
        "scene_ids": scene_ids,
        "entity_id": entity_id or None,
        "severity": severity,
        "category": category,
        "finding": _strip_json_escapes(finding),
        "citations": cits,
        "remedy": {
            "action": remedy_action,
            "detail": _strip_json_escapes(remedy_detail),
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

    if cap_problem := _umbrella_problem(category, scene_ids):
        return _reject_or_stop(tool_context, entity_id, category, cap_problem)

    if hedge_problem := _rating_marginal_gate(tool_context, category, finding, flag):
        return _reject_or_stop(tool_context, entity_id, category, hedge_problem)

    if split_problem := _sync_master_split_problem(category, finding, remedy_detail):
        _manifest_note(
            tool_context,
            {
                "guard": "sync_master_split",
                "stage": "filing",
                "category": category,
                "entity": entity_id,
            },
        )
        return _reject_or_stop(tool_context, entity_id, category, split_problem)

    if rule_problem := _normative_rule_problem(category, finding, remedy_detail):
        _manifest_note(
            tool_context,
            {
                "guard": "normative_filing",
                "stage": "filing",
                "category": category,
                "entity": entity_id,
                "matched": rule_problem[:160],
            },
        )
        return _reject_or_stop(tool_context, entity_id, category, rule_problem)

    if reg_problem := _unverified_regs(tool_context, finding):
        return _reject_or_stop(tool_context, entity_id, category, reg_problem)

    if statute_problem := _uncited_statute_problem(
        tool_context, category, finding, remedy_detail, cits
    ):
        _manifest_note(
            tool_context,
            {
                "guard": "uncited_statute",
                "stage": "filing",
                "category": category,
                "entity": entity_id,
                "matched": statute_problem[:120],
            },
        )
        return _reject_or_stop(tool_context, entity_id, category, statute_problem)

    if src_problem := _background_only_problem(severity, cits, tool_context):
        return _reject_or_stop(tool_context, entity_id, category, src_problem)
    if auth_problem := _authority_problem(severity, cits, category, tool_context):
        return _reject_or_stop(tool_context, entity_id, category, auth_problem)

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
            c["repaired"] = True  # on the record: this text was not the desk's
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

    cits = _prune_weak_citations(cits, category, tool_context)
    flag["citations"] = cits

    cost_span_max = 50
    if est_cost_usd_low > 0 and est_cost_usd_high > cost_span_max * est_cost_usd_low:
        return _reject_or_stop(
            tool_context,
            entity_id,
            category,
            f"REJECTED, not filed: cost range {est_cost_usd_low}-{est_cost_usd_high} spans "
            f">{cost_span_max}x — that is two different remedies' costs merged into one range "
            "(e.g. a license fee and its indie alternative). Give the range for the "
            "RECOMMENDED remedy only; name the alternative and its figure in remedy_detail.",
        )

    known = {s["scene_id"] for s in tool_context.state.get("scenes", [])}
    if bad := [s for s in scene_ids if s not in known]:
        return _reject_or_stop(
            tool_context,
            entity_id,
            category,
            f"REJECTED, not filed: unknown scene ids {bad}. Use ids from your worklist.",
        )

    _state_append(tool_context, f"flags:{_agent_key(tool_context)}", flag)
    _mark_work_item(tool_context, work_item_id)
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
        connect_timeout=15,
        send_receive_timeout=60,
    )


def _embed(text: str) -> list[float]:
    """Embed text with Vertex — must match the model used at corpus ingest time.
    Pinned to its own region: text-embedding-005 is not served from the global
    endpoint that the Gemini calls use for DSQ headroom."""
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("EMBED_LOCATION", "us-central1"),
        http_options=genai_types.HttpOptions(
            timeout=60_000,
            retry_options=genai_types.HttpRetryOptions(attempts=4, initial_delay=2),
        ),
    )
    res = client.models.embed_content(model="text-embedding-005", contents=text)
    return list(res.embeddings[0].values)


_BASE_RATES_CACHE: dict[str, dict[str, float]] = {}


def _corpus_base_rates() -> dict[str, float]:
    """Rating distribution across the rationale corpus (the same table the
    comparables come from — one denominator, run 17)."""
    if "rates" not in _BASE_RATES_CACHE:
        try:
            rows = (
                _clickhouse_client()
                .query("SELECT rating, count() FROM cara_rationales GROUP BY rating")
                .result_rows
            )
            total = sum(int(c) for _, c in rows) or 1
            _BASE_RATES_CACHE["rates"] = {r: round(100 * int(c) / total, 1) for r, c in rows}
        except Exception:
            _BASE_RATES_CACHE["rates"] = {}
    return _BASE_RATES_CACHE["rates"]


async def query_precedent(text: str, k: int, tool_context: ToolContext) -> dict[str, Any]:
    """Find the k released films whose OFFICIAL CARA rating rationale is
    nearest to this script's content profile — 4,733 films with their
    filmratings.com rationale, embedded in rationale-space.

    text: the CARA-style rationale you would file for THIS script — the same
    descriptor phrasing rating_boundary parses: intensity + category with
    framing qualifiers, e.g. "for strong bloody violence, pervasive language,
    and brief drug use". Derive intensities from the measured census, not
    impression. Do NOT send genre, plot, or setting — the corpus is official
    rationale strings, and only descriptor phrasing lands in the right
    neighbourhood ("a heist comedy with..." matches nothing).
    k: how many comparables, typically 8.

    Returns released films with their actual rating, the film's OFFICIAL CARA
    rationale (this IS the board's own wording — quote it verbatim as the
    excerpt, source_url attached), and distance (smaller = more similar; 0.0
    means a film was rated with this exact phrase). Cite with source_type
    "precedent" and via "clickhouse". Distance ~0 neighbours carrying a
    different rating than the majority are signal, not noise — the same
    profile drew different ratings (often era drift); say so rather than
    hiding the split. If you get an error field back, the corpus is
    unavailable: fall back to research() on documented CARA standards.
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
            FROM cara_rationales
            WHERE lower(title) != lower(%(skip_title)s)
            ORDER BY distance ASC, year DESC
            LIMIT %(k)s
            """,
                    parameters={
                        "vec": vec,
                        "k": max(1, min(int(k), 20)),
                        "skip_title": str(tool_context.state.get("script_title") or ""),
                    },
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


def _own_or_family(tool_context: ToolContext, prefix: str) -> Any:
    """Read a per-agent key, preferring THIS agent's own value and falling back
    to any instance in the desk family.

    query_precedent and rating_boundary write under _agent_key (the full agent
    name); file_rating_prediction read under _desk. Identical for the plain
    ratings_board worker, never for ratings_board__retry — so after a ratings
    collapse the retry's own query_precedent landed in
    last_precedent:ratings_board__retry while the filing read
    last_precedent:ratings_board, and EVERY prediction was rejected with "no
    comparables on record" until the retry hit its iteration cap. The report
    then shipped with no rating panel, precisely on the runs that had already
    failed once.
    """
    own = tool_context.state.get(f"{prefix}:{_agent_key(tool_context)}")
    if own:
        return own
    for name in batch_agent_names(_desk(tool_context)):
        if val := tool_context.state.get(f"{prefix}:{name}"):
            return val
    return None


# --- file_rating_prediction -------------------------------------------------


_NEAR_IDENTITY_DISTANCE = 0.30  # below this, the neighbour may be the same story


def comps_weighted_majority(comparables: list[dict[str, Any]]) -> str:
    """THE voting rule over comparables — inverse-distance weighted. Public
    because it must be the only one: the live prediction, the What-If
    simulator, and any render of "what do the neighbours say" share it, or
    the same neighbours produce different answers (they did)."""
    return _comps_weighted_majority(comparables)


def _comps_weighted_majority(comparables: list[dict[str, Any]]) -> str:
    """Distance-weighted majority rating of the comparables — the evidence's
    own verdict, which a prediction must either follow or explicitly rebut."""
    weights: dict[str, float] = {}
    for c in comparables:
        r = c.get("rating") or ""
        d = float(c.get("distance") or 1.0)
        weights[r] = weights.get(r, 0.0) + 1.0 / (d + 0.05)
    return max(weights, key=lambda k: weights[k]) if weights else ""


def file_rating_prediction(
    predicted: str,
    rationale: str,
    beats_to_cut: list[str],
    tool_context: ToolContext,
    divergence_reason: str = "",
) -> str:
    """File the MPA rating prediction for the report. Ratings Board only; call once,
    after query_precedent has returned comparables.

    predicted: the rating this screenplay draws as written: G | PG | PG-13 | R | NC-17.
    rationale: one sentence in CARA house style, e.g. "for strong language throughout,
      drug use and brief violence" — derived from your counted findings.
    beats_to_cut: if the production's target rating (in your instructions) is below
      `predicted`, the exact changes that buy the target, most impactful first, e.g.
      "Cut 2 of the 3 F-bombs; keep Danny's in S011". Empty list if already at target.

    divergence_reason: REQUIRED when your prediction differs from the
      comparables' distance-weighted majority rating — state specifically why
      the evidence doesn't govern (e.g. "comps match on setting but all are
      comedies where drinking is the joke; CARA's documented drug-depiction
      standard controls here"). Empty when you follow the evidence.

    The comparables from your most recent query_precedent call are attached
    automatically as the evidence. Filing without comparables is rejected, and
    a prediction that contradicts its own evidence without a stated reason is
    rejected — the report's claim is "evidence, not opinion".
    """
    # run-13 item 2: the cut list bypassed the filing gate and carried the
    # normative rules the finding gate had banned. Same contract: a beat is an
    # ACTION ("Cut X at S024"); the rule it serves lives in the finding, once.
    offending = [(b, m.group(0)) for b in beats_to_cut if (m := _NORMATIVE_RULE_RE.search(b or ""))]
    if offending:
        _manifest_note(
            tool_context,
            {
                "guard": "normative_cutlist",
                "stage": "filing",
                "matched": "; ".join(m for _, m in offending)[:160],
            },
        )
        listing = "\n- ".join(f'"{b[:90]}" (asserts: {m})' for b, m in offending)
        return (
            "REJECTED, not filed: these cut-list beats assert a CARA rule — a beat is "
            "the ACTION alone (what to cut/replace/restage, named by scene); naming the "
            "TARGET is fine ('…to target PG-13'), asserting the rule is not. Rewrite and "
            "refile once:\n- " + listing
        )

    comparables = _own_or_family(tool_context, "last_precedent")
    if not comparables:
        return (
            "REJECTED: no comparables on record. Call query_precedent first — the "
            "prediction's evidence is the nearest released films, not your judgement."
        )
    if predicted not in {"G", "PG", "PG-13", "R", "NC-17"}:
        return "REJECTED: predicted must be one of G, PG, PG-13, R, NC-17."
    majority = _comps_weighted_majority(comparables)
    boundary_set = _own_or_family(tool_context, "boundary_set") or []
    nearest = comparables[0] if comparables else None
    near_conflict = bool(
        nearest
        and float(nearest.get("distance") or 1.0) < _NEAR_IDENTITY_DISTANCE
        and nearest.get("rating")
        and nearest["rating"] != predicted
    )
    outside_boundary = bool(boundary_set) and predicted not in boundary_set
    if (
        (majority and predicted != majority) or near_conflict or outside_boundary
    ) and not divergence_reason.strip():
        tally: dict[str, int] = {}
        for c in comparables:
            tally[c["rating"]] = tally.get(c["rating"], 0) + 1
        near_note = (
            f" Your NEAREST comparable, '{nearest['title']}' at distance "
            f"{nearest['distance']}, is rated {nearest['rating']} — close enough that "
            "it may be this very story's released form; a rating that contradicts it "
            "must say why (a draft often overshoots its released cut — if that is the "
            "case, say so and point at the cut list)."
            if near_conflict
            else ""
        )
        boundary_note = (
            f" The measured CARA boundary's conformal prediction set is {boundary_set} "
            "(90% coverage guarantee) and your prediction sits outside it."
            if outside_boundary
            else ""
        )
        legs = []
        if majority and predicted != majority:
            legs.append(f"the comparables' weighted majority is {majority} (tally: {tally})")
        if near_conflict:
            legs.append("your nearest comparable conflicts (see below)")
        if outside_boundary:
            legs.append("your prediction sits outside the conformal set (see below)")
        return (
            f"REJECTED: your prediction {predicted} fails the evidence contract on: "
            + "; ".join(legs)
            + f".{near_note}{boundary_note} "
            "Either follow the evidence, or refile with divergence_reason stating "
            "specifically why the failing leg doesn't govern."
        )
    meta = _own_or_family(tool_context, "last_precedent_meta") or {}
    tool_context.state["rating_prediction"] = {
        "predicted": predicted,
        "target": tool_context.state.get("target_rating"),
        "rationale": rationale,
        "comparables": comparables,
        "beats_to_cut": list(beats_to_cut),
        "corpus_base_rates": meta.get("base_rates") or {},
        "distance_spread": meta.get("spread"),
        "comps_majority": majority,
        "conformal_set": list(boundary_set),
        "divergence_reason": divergence_reason.strip(),
        "nearest_conflict": (
            {
                "title": nearest.get("title", ""),
                "rating": nearest.get("rating", ""),
                "distance": nearest.get("distance"),
            }
            if near_conflict
            else None
        ),
    }
    dist: dict[str, int] = {}
    for c in comparables:
        dist[c["rating"]] = dist.get(c["rating"], 0) + 1
    return f"Prediction filed: {predicted}. Comparable ratings: {dist}."


# --- note_open_question -----------------------------------------------------


_OQ_NEG = (
    "unclear",
    "unknown",
    "unable",
    "cannot",
    "can't",
    "couldn't",
    "could not",
    "pending",
    "unverified",
    "needs further",
    "needs manual",
    "open question",
)


def _reads_as_determination(q: str) -> bool:
    """A note that states a closed conclusion ("Cleared.", "no license required")
    rather than an unresolved item. Mirrors binder._is_determination / report.js."""
    t = (q or "").strip()
    if t.endswith("?"):
        return False
    low = t.lower()
    if any(neg in low for neg in _OQ_NEG):
        return False
    if re.search(r"\bcleared\b", low):
        return True
    return bool(
        re.search(
            r"\bno (?:synchronization|sync|master(?:[- ]use)?|licen[cs]e|clearance"
            r"|release|permit|action)\b[^.?]*\b(?:required|needed|necessary)\b",
            low,
        )
    )


def note_open_question(question: str, tool_context: ToolContext, work_item_id: str = "") -> str:
    """Record something you could NOT resolve. Surfaced in the report as an honest
    unknown — an honest unknown beats a confident guess. Use when research was
    inconclusive or the answer needs a human (e.g. ownership deeper than 3 hops).
    NOT for conclusions: "cleared" or "no license required" is a determination and
    belongs in record_clearance, never here — file each conclusion exactly once."""
    question = _strip_json_escapes(question)
    if _reads_as_determination(question):
        return (
            "NOT NOTED: that reads as a closed determination, not an open question. "
            "If the item is resolved, record it once with record_clearance and do not "
            "also note it here. If it is genuinely unresolved, restate it as what "
            "remains unknown."
        )
    _state_append(tool_context, f"open_questions:{_agent_key(tool_context)}", question)
    _mark_work_item(tool_context, work_item_id)
    return "Noted."


# --- done -------------------------------------------------------------------


_DONE_MIN_BUDGET = 3


_MIN_KEYWORD = 2  # 'of', 'in' would match everything
_CSATF_CACHE: dict[str, dict[str, str]] = {}


def _csatf_index() -> dict[str, str]:
    if "b" not in _CSATF_CACHE:
        import json as _json
        from pathlib import Path as _Path

        data = _json.loads(
            (_Path(__file__).resolve().parents[1] / "data" / "csatf_bulletins.json").read_text()
        )
        _CSATF_CACHE["b"] = data["bulletins"]
    return _CSATF_CACHE["b"]


_BOUNDARY_CACHE: dict[str, Any] = {}


def _boundary_data() -> dict[str, Any]:
    if "d" not in _BOUNDARY_CACHE:
        import json as _json
        from pathlib import Path as _Path

        _BOUNDARY_CACHE["d"] = _json.loads(
            (_Path(__file__).resolve().parents[1] / "data" / "rating_boundary.json").read_text()
        )
    return _BOUNDARY_CACHE["d"]


def _parse_descriptor(desc: str, vocab: dict[str, Any]) -> tuple[str, str] | None:
    """(intensity, category) via the SAME vocabulary the corpus was parsed
    with (embedded in the asset), so runtime phrasing and harvest phrasing
    cannot silently diverge. Returns None when no category variant matches."""
    seg = re.sub(r"[^a-z0-9 ]", " ", (desc or "").lower())
    seg = " ".join(seg.split())
    if not seg:
        return None
    intensity = ""
    for i in vocab.get("intensities") or []:
        if re.search(rf"\b{re.escape(i)}\b", seg):
            intensity = i
            break
    cat, best = "", 0
    for c, variants in (vocab.get("categories") or {}).items():
        for v in variants:
            if v in seg and len(v) > best:
                cat, best = c, len(v)
    if not cat:
        return None
    return (intensity or "unmodified", cat)


# The derived corpus is cited by name — it is ScriptRisk's own aggregate, not
# filmratings.com. filmratings.com is the provenance of the underlying rationales;
# the 4,544-rationale marginal is our derivation, and a reader must be able to tell
# the two corpora apart from the ratings corpus (6,302 released films) used for kNN.
_CARA_CORPUS = "ScriptRisk CARA descriptor corpus: 4,544 official CARA rationales, filmratings.com"


def boundary_eval(descriptors: list[str]) -> dict[str, Any]:
    """Pure boundary evaluation for a set of CARA-style descriptor phrases —
    the same marginals + conformal math as rating_boundary, with no session
    state and no citation registry. Built for the What-If simulator (run 17):
    a post-cut rationale is too sparse for text-neighbor kNN, and this measured
    instrument is the honest one there."""
    import math as _math

    d = _boundary_data()
    vocab = d.get("vocabulary") or {}
    feats = d["model"]["features"]
    idx = {k: i for i, k in enumerate(feats)}
    x = [0.0] * (len(feats) + 1)
    x[-1] = 1.0
    matched: list[str] = []
    unmatched: list[str] = []
    marginals: dict[str, Any] = {}
    for desc in descriptors:
        parsed = _parse_descriptor(desc, vocab)
        if parsed is None:
            unmatched.append(desc)
            continue
        intensity, cat = parsed
        matched.append(desc)
        for key in (f"{intensity} {cat}", cat):
            m = d["marginals"].get(key)
            if m and key not in marginals:
                n = sum(m.values())
                marginals[key] = {
                    "descriptor": key,
                    "n": n,
                    "distribution": {
                        r: f"{100 * c // n}%" for r, c in sorted(m.items(), key=lambda kv: -kv[1])
                    },
                }
        for cand in (f"{intensity} {cat}", cat):
            if cand in idx:
                x[idx[cand]] = 1.0
    z = [sum(wc[j] * x[j] for j in range(len(x)) if x[j]) for wc in d["model"]["weights"]]
    mx = max(z)
    e = [_math.exp(v - mx) for v in z]
    ssum = sum(e)
    probs = {c: e[i] / ssum for i, c in enumerate(d["model"]["classes"])}
    pred_set = [
        c
        for i, c in enumerate(d["model"]["classes"])
        if 1.0 - probs[c] <= d["model"]["conformal_q"][str(i)]
    ]
    return {
        "matched": matched,
        "unmatched": unmatched,
        "marginals": marginals,
        "probabilities": {c: round(v, 3) for c, v in sorted(probs.items(), key=lambda kv: -kv[1])},
        "prediction_set": pred_set,
    }


def rating_boundary(descriptors: list[str], tool_context: ToolContext) -> dict[str, Any]:
    """Measured CARA decision boundary: per-descriptor rating distributions across
    4,544 official post-1990 rationales, plus the fitted model's conformal prediction
    set for the combination. This is EVIDENCE. Each matched marginal returns a ready
    `citation` sentence carrying the numbers — file THAT verbatim as the finding's
    citation; name only the descriptor in your finding prose, never the percentage
    (a loose number the verifier cannot trace to the corpus is what gets rejected).
    Free (no research budget). Call BEFORE file_rating_prediction; a prediction outside
    the conformal set needs a stated divergence reason.

    descriptors: CARA-style intensity+category phrases matching what you
    counted, e.g. ["pervasive language", "some violence", "brief nudity"].
    The return names matched_descriptors and unmatched_descriptors — if any
    came back unmatched, rephrase them and call again; the prediction set is
    only a filing gate when EVERY descriptor matched.
    """
    import math as _math

    d = _boundary_data()
    vocab = d.get("vocabulary") or {}
    marginals = {}
    feats = d["model"]["features"]
    idx = {k: i for i, k in enumerate(feats)}
    x = [0.0] * (len(feats) + 1)
    x[-1] = 1.0
    matched: list[str] = []
    unmatched: list[str] = []
    for desc in descriptors:
        parsed = _parse_descriptor(desc, vocab)
        if parsed is None:
            unmatched.append(desc)
            continue
        intensity, cat = parsed
        matched.append(desc)
        for key in (f"{intensity} {cat}", cat):
            m = d["marginals"].get(key)
            if m:
                n = sum(m.values())
                dist = {r: f"{100 * c // n}%" for r, c in sorted(m.items(), key=lambda kv: -kv[1])}
                # The desk cites THIS sentence verbatim (registered as provenance
                # below), so a rating finding's percentage lives in a citation the
                # verifier can trace to the corpus — never loose in the finding prose,
                # where it read as an unsupported statistic and got rejected. The number
                # appears in exactly one place, attributed to our derived corpus by name.
                dist_str = ", ".join(f"{r} {p}" for r, p in dist.items())
                sentence = (
                    f"'{key}': {dist_str} across {n} official CARA rationales ({_CARA_CORPUS})"
                )
                marginals[key] = {"n": n, "distribution": dist, "citation": sentence}
                # typed registry: only sentences emitted HERE earn the marginal tier
                _marginal_bucket(tool_context).add(_norm_for_match(sentence))
        for cand in (f"{intensity} {cat}", cat):
            if cand in idx:
                x[idx[cand]] = 1.0
    # Structured marginals for file_flag to attach (run-13 item 3): the field is
    # populated by THIS tool's last result, keyed per agent — never typed by the
    # model. base_rate = the descriptor corpus' own rating shares.
    totals = d.get("rating_totals") or {}
    tsum = sum(totals.values()) or 1
    base_rate = {r: f"{100 * c // tsum}%" for r, c in sorted(totals.items(), key=lambda kv: -kv[1])}
    tool_context.state[f"marginal_last:{_agent_key(tool_context)}"] = {
        key: {
            "descriptor": key,
            "n": m["n"],
            "distribution": m["distribution"],
            "base_rate": base_rate or None,
            "source": "ScriptRisk CARA descriptor corpus (4,544 official rationales)",
        }
        for key, m in marginals.items()
    }
    z = [sum(wc[j] * x[j] for j in range(len(x)) if x[j]) for wc in d["model"]["weights"]]
    mx = max(z)
    e = [_math.exp(v - mx) for v in z]
    ssum = sum(e)
    probs = {c: e[i] / ssum for i, c in enumerate(d["model"]["classes"])}
    pred_set = [
        c
        for i, c in enumerate(d["model"]["classes"])
        if 1.0 - probs[c] <= d["model"]["conformal_q"][str(i)]
    ]
    # The set hard-gates file_rating_prediction ONLY when every descriptor
    # matched: a set built from silently-dropped inputs once rejected a desk's
    # correct R prediction as "outside the evidence". Partial input = advisory.
    complete = bool(matched) and not unmatched
    tool_context.state[f"boundary_set:{_agent_key(tool_context)}"] = pred_set if complete else []
    out: dict[str, Any] = {
        "matched_descriptors": matched,
        "unmatched_descriptors": unmatched,
        "marginals": marginals,
        "model_probabilities": {
            c: round(pv, 3) for c, pv in sorted(probs.items(), key=lambda kv: -kv[1])
        },
        "conformal_prediction_set": pred_set,
        "source": _CARA_CORPUS,
    }
    if unmatched:
        # Every unmatched descriptor is a rating driver that loses its measured
        # marginal and falls back to qualitative language. Log the misses so the
        # vocabulary can be aliased to cover the phrasings desks actually use.
        _LOG.info("rating_boundary unmatched descriptors: %s", unmatched)
        out["warning"] = (
            f"{len(unmatched)} descriptor(s) did not match the measured vocabulary "
            f"({unmatched}); the prediction set EXCLUDES them and is advisory only, "
            "not a guarantee. Rephrase (e.g. 'drug content' -> 'drug use', "
            "'thematic elements' -> 'thematic material') and call again."
        )
    elif not matched:
        out["warning"] = (
            "no descriptors given or matched — this is the base-rate prior only, "
            "not a guarantee. Provide CARA-style descriptors."
        )
    else:
        out["coverage_note"] = (
            "the true rating falls inside the prediction set at least 90% of the "
            "time per pooled rating group ({G,PG}, {PG-13}, {R,NC-17}) by "
            "construction (pooled Mondrian split conformal, 937 held-out films; "
            "aggregate coverage 92%). G and NC-17 are too rare post-1990 for "
            "single-class guarantees — see the methodology page's per-class table."
        )
    _register_tool_output(tool_context, out)
    return out


_BBFC_CACHE: dict[str, Any] = {}
_BBFC_HITS = 8


def bbfc_cut_precedent(content: str, tool_context: ToolContext) -> dict[str, Any]:
    """Regulator-documented cut precedents: BBFC's published records of which
    cuts were made and what category they achieved. Use to ground a cut-list
    item ("films that made this exact cut moved 15 -> 12A") or a territory
    UK finding. Free (no research budget). Cite as
    "BBFC published cuts record: <title> (<year>)".

    content: what the cut concerns — e.g. "strong language", "violence".
    """
    if "r" not in _BBFC_CACHE:
        import json as _json
        from pathlib import Path as _Path

        _BBFC_CACHE["r"] = _json.loads(
            (_Path(__file__).resolve().parents[1] / "data" / "bbfc_cuts.json").read_text()
        )["records"]
    words = [
        w for w in re.sub(r"[^a-z0-9 ]", " ", content.lower()).split() if len(w) > _MIN_KEYWORD
    ]
    hits = [
        r
        for r in _BBFC_CACHE["r"]
        if r.get("what_was_cut") and any(w in r["what_was_cut"].lower() for w in words)
    ]
    hits.sort(key=lambda r: (r.get("uncut_available") is None, -(r.get("year") or 0)))
    out = {
        "matches": hits[:_BBFC_HITS],
        "total_records": len(_BBFC_CACHE["r"]),
        "source": "BBFC published cuts records, bbfc.co.uk",
    }
    _register_tool_output(tool_context, out)
    return out


def csatf_bulletin(topic: str, tool_context: ToolContext) -> dict[str, Any]:
    """Look up CSATF safety bulletin numbers by topic — the official index,
    checked in from csatf.org. ALWAYS use this before citing a bulletin number;
    numbers from memory have been wrong. Free (no research budget).

    topic: keywords, e.g. "water", "open flame", "minors", "firearms".
    Returns matching bulletins as {number: title}. Cite as
    "CSATF Safety Bulletin #<number>: <title>" — but a title line is number
    verification, NOT substantive support: pair it with research() into the
    bulletin's actual requirements, or the verifier will reject the flag.
    """
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", topic.lower()).split() if len(w) > _MIN_KEYWORD]
    idx = _csatf_index()
    hits = {num: title for num, title in idx.items() if any(w in title.lower() for w in words)}
    if not hits:
        return {
            "matches": {},
            "guidance": "No bulletin title matches. Broaden the keywords, or cite the "
            "hazard without a bulletin number rather than guessing one.",
        }
    out = {"matches": hits}
    _register_tool_output(tool_context, out)
    return out


def verify_trademark(number: str, tool_context: ToolContext) -> dict[str, Any]:
    """Verify a US trademark registration or serial number against the USPTO
    register (TSDR). REQUIRED before citing any registration number in a
    finding — file_flag rejects findings citing unverified numbers. Free.

    number: digits only — a registration number (e.g. "1001109") or an
    8-digit serial number.
    Returns the mark text, LIVE/DEAD status, current owner, and both numbers.
    An attorney_of_record_email, when present, is the USPTO prosecution
    correspondent — NEVER present it as a licensing contact; remedies should
    direct the production to the owner's licensing department, unnamed.
    An error field means the number did not resolve: do not cite it.
    """
    digits = re.sub(r"[^0-9]", "", str(number))
    if not digits:
        return {"error": "no digits in the number given"}
    state = tool_context.state
    # Durable cache: trademark status moves on a months scale, popular marks
    # recur across scripts, and TSDR occasionally 503s — one register read
    # serves everyone for ~90 days.
    cache_key = f"tsdr-{digits}"
    cached = _durable_cache_load(cache_key)
    if cached and not cached.get("error") and _tsdr_cache_fresh(cached):
        result = dict(cached)
        result["cached"] = True
    else:
        result = _tsdr_lookup(digits)
        if not result.get("error"):
            result["fetched_at"] = time.strftime("%Y-%m-%d")
            _durable_cache_store(cache_key, result)
    if not result.get("error"):
        seen = list(state.get(f"verified_marks:{_agent_key(tool_context)}", []) or [])
        if digits not in seen:
            seen.append(digits)
        state[f"verified_marks:{_agent_key(tool_context)}"] = seen
        _register_provenance(tool_context, [str(v) for v in result.values() if v])
    return result


_TSDR_CACHE_DAYS = 90


def _tsdr_cache_fresh(record: dict[str, Any]) -> bool:
    import datetime as _dt

    try:
        fetched = _dt.date.fromisoformat(record.get("fetched_at", ""))
    except ValueError:
        return False
    return (_dt.date.today() - fetched).days <= _TSDR_CACHE_DAYS


_SERIAL_LEN = 8  # USPTO serial numbers; registration numbers are shorter


def _tsdr_lookup(digits: str) -> dict[str, Any]:
    """USPTO TSDR status lookup via the server-rendered statusview page —
    the JSON API paths 404 as of 2026-08; the HTML is stable and richer.
    Module-level so tests can monkeypatch."""
    import urllib.error
    import urllib.request
    from http import HTTPStatus

    kind = "sn" if len(digits) == _SERIAL_LEN else "rn"
    url = f"https://tsdr.uspto.gov/statusview/{kind}{digits}"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (ScriptRisk clearance research)"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == HTTPStatus.NOT_FOUND:
            return {"error": f"number {digits} not found on the USPTO register"}
        return {"error": f"USPTO lookup failed: HTTP {e.code}"}
    except Exception as exc:
        return {"error": f"USPTO lookup failed: {type(exc).__name__}"}

    def grab(pattern: str) -> str:
        m2 = re.search(pattern, html, re.S)
        return re.sub(r"\s+", " ", m2.group(1)).strip() if m2 else ""

    mark = grab(r'Mark:</div>\s*<div class="value markText">\s*(.*?)\s*</div>')
    live_dead = grab(r"((?:LIVE|DEAD)/[A-Za-z/ ]+)")
    status = grab(r'Status:</div>\s*<div class="value single">\s*(.*?)\s*</div>')
    owner = grab(r"Owner Name:</div>\s*<div class=\"value\">\s*(.*?)\s*</div>") or grab(
        r"\b([A-Z][A-Z&,.' ]{4,60}(?:LLC|INC|CORP|COMPANY|CO\.|LTD))\b"
    )
    contact = grab(r"mailto:([^\"']+)")
    reg_no = grab(r"US Registration Number:</div>\s*<div class=\"value\">\s*([0-9]+)")
    serial = grab(r"US Serial Number:</div>\s*<div class=\"value\">\s*([0-9]+)")
    if not mark:
        return {"error": f"number {digits} did not resolve to a mark on TSDR"}
    out = {
        "number": digits,
        "mark": mark,
        "live_dead": live_dead,
        "status": status,
        "owner": owner,
        "registration_number": reg_no,
        "serial_number": serial,
    }
    if contact:
        # TSDR's mailto is the prosecution correspondent of record — typically an
        # outside-counsel docketing inbox, NOT the brand's licensing office. A wrong
        # contact is worse than none, so it is labeled for what it is.
        out["attorney_of_record_email"] = contact
        out["contact_note"] = (
            "attorney_of_record_email is the USPTO correspondence address for this "
            "registration (often outside counsel's docketing inbox). Never present it "
            "as a licensing contact; remedies should direct the production to the "
            "owner's licensing or brand-partnership department, unnamed."
        )
    return out


def record_clearance(
    entity_id: str, reasoning: str, tool_context: ToolContext, work_item_id: str = ""
) -> str:
    """Record that a worklist item was examined and CLEARED — no finding needed.

    This is how examined-and-fine work becomes visible: silence looks identical to
    "never looked". Use it for every worklist item you investigated and concluded
    carries no issue (public domain, generic term, protected expressive use, no
    real-world match). NOT for unresolved items — those are note_open_question.

    entity_id: the worklist entity this clears (e.g. "E014"), or "" for a
      script-level determination.
    work_item_id: the worklist item this dispositions (e.g. "TC-AX-CN-SUPERNATURAL")
      — pass it whenever your worklist item shows one.
    reasoning: one or two sentences stating WHY it is clear, specific enough for
      production counsel to audit ("'Amazing Grace' composition published 1779,
      public domain worldwide; no specific recording is used").
    """
    desk = _desk(tool_context)
    name = _agent_key(tool_context)
    state = tool_context.state
    entry = {
        "entity_id": entity_id or None,
        "work_item_id": work_item_id or None,
        "reasoning": _clip_words(_strip_json_escapes((reasoning or "").strip()), 600),
    }
    if not entry["reasoning"]:
        return "REJECTED: reasoning is required — a bare 'cleared' is not auditable."
    cleared = list(state.get(f"cleared:{name}", []) or [])
    cleared.append(entry)
    state[f"cleared:{name}"] = cleared
    _mark_work_item(tool_context, work_item_id)
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
    if name.endswith("__sweep"):
        worklist = list(state.get("sweep_worklist") or [])
    elif name.endswith("__retry"):
        worklist = list(state.get(f"retry_worklist:{desk}") or [])
    elif idx is not None:
        slices = clearance_batch_slices(state)
        worklist = slices[idx] if idx < len(slices) else []
    else:
        worklist = _triage_dict(state).get(desk) or []
    budget_left = int(state.get(_budget_key(tool_context), 0))
    covered: set[str] = set()
    for f in state.get(f"flags:{name}", []) or []:
        if f.get("entity_id"):
            covered.add(f["entity_id"])
    for c in state.get(f"cleared:{name}", []) or []:
        if c.get("entity_id"):
            covered.add(c["entity_id"])
    oq_texts = [str(q).lower() for q in state.get(f"open_questions:{name}", []) or []]
    wi_covered = set(state.get(f"wi_done:{name}") or [])

    def _addressed(item: Any) -> bool:
        if not isinstance(item, dict):
            return True
        wid = item.get("work_item_id")
        if wid and wid in wi_covered:
            return True
        if item.get("entity_id") in covered:
            return True
        surface = (item.get("surface") or "").lower()
        return bool(surface) and any(surface in q for q in oq_texts)

    missing = [w for w in worklist if not _addressed(w)]
    # The Summers failure: desks clear the easy people and swallow the hard
    # ones. Refusals name names, negatively-depicted persons first.
    name_cap = 10

    def _hard_person(w: dict[str, Any]) -> bool:
        return w.get("portrayal") in ("unflattering", "criminal_or_fraudulent") or bool(
            w.get("depicted_negatively")
        )

    missing.sort(
        key=lambda w: (
            not _hard_person(w),
            w.get("prominence") != "PLOT_CRITICAL",
        )
    )
    # No refusal cap: closing with undispositioned items is not a thing a desk
    # can talk its way into — the LoopAgent iteration ceiling is the hard stop.
    if missing and budget_left >= _DONE_MIN_BUDGET:
        state[f"done_refusals:{name}"] = refusals + 1
        named = "; ".join(
            (
                f"{w.get('work_item_id') or w.get('entity_id')} "
                f"'{w.get('surface') or str(w.get('note') or '')[:60]}'"
            )
            + (" — NEGATIVELY PORTRAYED, this one cannot be skipped" if _hard_person(w) else "")
            for w in missing[:name_cap]
        )
        more = f" (+{len(missing) - name_cap} more)" if len(missing) > name_cap else ""
        return (
            f"NOT CLOSED: {len(missing)} worklist items have NO disposition — every one "
            f"needs file_flag, record_clearance, or note_open_question (pass the item's "
            f"work_item_id). Unaddressed: {named}{more}. "
            f"{budget_left} research budget remains."
        )
    if not name.endswith(("__sweep", "__retry")):
        # Sweeper and retry desks must NOT escalate: escalation bubbles past
        # their own agent and would end the completeness gate's loop early.
        tool_context.actions.escalate = True
    return f"Desk closed: {reason}"


DESK_TOOLS = [
    read_scene,
    find_in_script,
    research,
    record_clearance,
    csatf_bulletin,
    verify_trademark,
    rating_boundary,
    bbfc_cut_precedent,
    fetch_page,
    deep_research,
    query_precedent,
    file_rating_prediction,
    file_flag,
    note_open_question,
    done,
]

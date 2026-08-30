"""Durable run state (ADR-1 Phase 1): writer-run status in Firestore.

Memory stays the fast path; Firestore makes status survive restarts and lets a
poll land on any instance. Everything degrades gracefully — no Firestore, no
crash, exactly like the storage layer.
"""

from __future__ import annotations

import os
import time
from typing import Any

_cache: dict = {}
COLLECTION = "writer_runs"


def _db():
    if "db" not in _cache:
        from google.cloud import firestore

        _cache["db"] = firestore.Client()
    return _cache["db"]


def set_state(run_id: str, state: dict[str, Any]) -> bool:
    try:
        doc = {k: v for k, v in state.items() if k != "record"}  # records live in GCS
        _db().collection(COLLECTION).document(run_id).set(doc, merge=True)
        return True
    except Exception:
        return False


COUNTERS_DOC = ("metrics", "lifetime")


def increment(counter: str, by: int = 1) -> bool:
    """Durable all-time counters (runs, fixes, errors...) — atomic Firestore
    increments, so restarts and redeploys stop zeroing the history."""
    try:
        from google.cloud import firestore

        _db().collection(COUNTERS_DOC[0]).document(COUNTERS_DOC[1]).set(
            {counter: firestore.Increment(by)}, merge=True
        )
        return True
    except Exception:
        return False


def get_counters() -> dict[str, Any]:
    try:
        snap = _db().collection(COUNTERS_DOC[0]).document(COUNTERS_DOC[1]).get()
        return snap.to_dict() or {}
    except Exception:
        return {}


def get_state(run_id: str) -> dict[str, Any] | None:
    try:
        snap = _db().collection(COLLECTION).document(run_id).get()
        return snap.to_dict() if snap.exists else None
    except Exception:
        return None


# ---------------------------------------------------------------- clearance runs
# ADR-1 Phase 2: clearance-run state + an append-only event journal, so a run's
# progress survives instance restarts and can be relayed from ANY instance (or
# written by a worker job that shares nothing with the web tier).

RUNS_COLLECTION = "clearance_runs"

# One journal doc per flush, not per event: Firestore sustains ~1 write/sec per
# document, and a desk burst emits far more events than that. Chunks keep the
# write rate safe and the read path a simple ordered scan.


def run_set(run_id: str, state: dict[str, Any]) -> bool:
    try:
        _db().collection(RUNS_COLLECTION).document(run_id).set(state, merge=True)
        return True
    except Exception:
        return False


def run_get(run_id: str) -> dict[str, Any] | None:
    try:
        snap = _db().collection(RUNS_COLLECTION).document(run_id).get()
        return snap.to_dict() if snap.exists else None
    except Exception:
        return None


def events_append(run_id: str, first_seq: int, events: list[dict[str, Any]]) -> bool:
    """One chunk of the journal. first_seq orders chunks; ids are zero-padded so
    lexicographic order equals numeric order."""
    try:
        (
            _db()
            .collection(RUNS_COLLECTION)
            .document(run_id)
            .collection("events")
            .document(f"{first_seq:08d}")
            .set({"first_seq": first_seq, "events": events})
        )
        return True
    except Exception:
        return False


def events_read(run_id: str, after_seq: int = -1) -> tuple[list[dict[str, Any]], int]:
    """Every event with seq > after_seq, in order, plus the new high-water mark."""
    try:
        chunks = (
            _db()
            .collection(RUNS_COLLECTION)
            .document(run_id)
            .collection("events")
            .order_by("first_seq")
            .stream()
        )
        out: list[dict[str, Any]] = []
        seq = after_seq
        for chunk in chunks:
            data = chunk.to_dict() or {}
            first = data.get("first_seq", 0)
            for i, ev in enumerate(data.get("events", [])):
                if first + i > after_seq:
                    out.append(ev)
                    seq = first + i
        return out, seq
    except Exception:
        return [], after_seq


# No legitimate run outlives this: a feature script finishes in ~12 minutes and
# the pipeline aborts after 15 minutes of agent silence. Anything still marked
# "running" past this window is abandoned, not slow.
RUN_MAX_AGE_S = float(os.getenv("RUN_MAX_AGE_S", str(90 * 60)))
_RUNNING_SCAN_LIMIT = 50


def _is_stale(state: dict[str, Any], cutoff: float) -> bool:
    started = float(state.get("started_at") or 0)
    return started > 0 and started < cutoff


def count_running(max_age_s: float = RUN_MAX_AGE_S) -> int:
    """Live clearance runs across ALL instances and workers — the concurrency
    cap must see the whole fleet, not one process's memory.

    ABANDONED runs are excluded. A worker killed by a task timeout, an OOM, or
    an instance death never writes a terminal status, so its doc reads "running"
    forever; counting those latched the cap closed permanently — five zombies
    and every new run 429s until someone hand-edits Firestore. Undercounting is
    the safe direction: it admits work, where overcounting refuses all of it.
    """
    try:
        cutoff = time.time() - max_age_s
        docs = (
            _db()
            .collection(RUNS_COLLECTION)
            .where("status", "==", "running")
            .limit(_RUNNING_SCAN_LIMIT)
            .stream()
        )
        return sum(1 for d in docs if not _is_stale(d.to_dict() or {}, cutoff))
    except Exception:
        return 0


def reap_stale(max_age_s: float = RUN_MAX_AGE_S) -> int:
    """Mark abandoned runs terminal so they stop counting, stop being polled by
    every viewer's relay, and stop rendering as live. Called at admission — rare,
    and exactly when a latched cap would otherwise refuse a paying user."""
    try:
        cutoff = time.time() - max_age_s
        docs = list(
            _db()
            .collection(RUNS_COLLECTION)
            .where("status", "==", "running")
            .limit(_RUNNING_SCAN_LIMIT)
            .stream()
        )
    except Exception:
        return 0
    reaped = 0
    for doc in docs:
        if not _is_stale(doc.to_dict() or {}, cutoff):
            continue
        if run_set(
            doc.id,
            {
                "status": "error",
                "message": "abandoned — worker exited without a terminal status",
                "finished_at": time.time(),
            },
        ):
            reaped += 1
    return reaped


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    """Newest clearance runs fleet-wide, any status — the admin page must see
    worker-owned runs too, which the web tier's memory deliberately drops."""
    try:
        from google.cloud import firestore

        docs = (
            _db()
            .collection(RUNS_COLLECTION)
            .order_by("started_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        return [{"id": d.id, **(d.to_dict() or {})} for d in docs]
    except Exception:
        return []

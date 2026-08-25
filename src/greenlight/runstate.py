"""Durable run state (ADR-1 Phase 1): writer-run status in Firestore.

Memory stays the fast path; Firestore makes status survive restarts and lets a
poll land on any instance. Everything degrades gracefully — no Firestore, no
crash, exactly like the storage layer.
"""

from __future__ import annotations

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


def get_state(run_id: str) -> dict[str, Any] | None:
    try:
        snap = _db().collection(COLLECTION).document(run_id).get()
        return snap.to_dict() if snap.exists else None
    except Exception:
        return None

"""Durable run storage on GCS: report links survive restarts and redeploys.

In-memory state stays the fast path; this is the layer under it. Every write
and read degrades gracefully — a missing bucket or credentials must never take
an endpoint down, it just means that record lives only as long as the process.
"""

from __future__ import annotations

import json
import os
from typing import Any

BUCKET = os.getenv("GREENLIGHT_BUCKET", "greenlight-clearance-2026-staging")

_cache: dict = {}


def _bucket():
    if "client" not in _cache:
        from google.cloud import storage as gcs

        _cache["client"] = gcs.Client()
    return _cache["client"].bucket(BUCKET)


def save_record(run_id: str, record: dict[str, Any]) -> bool:
    try:
        _bucket().blob(f"records/{run_id}.json").upload_from_string(
            json.dumps(record), content_type="application/json"
        )
        return True
    except Exception:
        return False


def load_record(run_id: str) -> dict[str, Any] | None:
    try:
        blob = _bucket().blob(f"records/{run_id}.json")
        if not blob.exists():
            return None
        return json.loads(blob.download_as_text())
    except Exception:
        return None


def save_script(run_id: str, source: str) -> bool:
    try:
        _bucket().blob(f"scripts/{run_id}.fountain").upload_from_string(
            source, content_type="text/plain"
        )
        return True
    except Exception:
        return False


def load_script(run_id: str) -> str | None:
    try:
        blob = _bucket().blob(f"scripts/{run_id}.fountain")
        if not blob.exists():
            return None
        return blob.download_as_text()
    except Exception:
        return None

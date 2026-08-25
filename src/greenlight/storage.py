"""Durable run storage on GCS: report links survive restarts and redeploys.

In-memory state stays the fast path; this is the layer under it. Every write
and read degrades gracefully — a missing bucket or credentials must never take
an endpoint down, it just means that record lives only as long as the process.
"""

from __future__ import annotations

import json
import os
from typing import Any

_USER_PATH_PARTS = 3  # users/{sub}/runs...
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


RESEARCH_TTL_S = 7 * 24 * 3600  # a week: fresh enough for citations, stable for reruns


def load_research(key: str) -> dict[str, Any] | None:
    """Cross-run research cache: the same clearance question re-asks the web at
    most weekly. Stabilizes reruns (same sources -> same verifier outcomes) and
    stops paying twice for the same question."""
    try:
        blob = _bucket().blob(f"research/{key}.json")
        if not blob.exists():
            return None
        data = json.loads(blob.download_as_text())
        import time as _t

        if _t.time() - data.get("_cached_at", 0) > RESEARCH_TTL_S:
            return None
        return data
    except Exception:
        return None


def save_research(key: str, record: dict[str, Any]) -> bool:
    try:
        import time as _t

        _bucket().blob(f"research/{key}.json").upload_from_string(
            json.dumps({**record, "_cached_at": _t.time()}), content_type="application/json"
        )
        return True
    except Exception:
        return False


# ---- per-user history: small stubs under users/{sub}/runs/ for cheap listing ----


def save_user_run(sub: str, run_id: str, stub: dict[str, Any]) -> bool:
    try:
        _bucket().blob(f"users/{sub}/runs/{run_id}.json").upload_from_string(
            json.dumps(stub), content_type="application/json"
        )
        return True
    except Exception:
        return False


def list_user_runs(sub: str) -> list[dict[str, Any]]:
    try:
        out = []
        for blob in _bucket().list_blobs(prefix=f"users/{sub}/runs/"):
            try:
                out.append(json.loads(blob.download_as_text()))
            except Exception:
                continue
        out.sort(key=lambda r: r.get("generated_at") or "", reverse=True)
        return out
    except Exception:
        return []


def save_user_profile(sub: str, profile: dict[str, Any]) -> bool:
    try:
        _bucket().blob(f"users/{sub}/profile.json").upload_from_string(
            json.dumps(profile), content_type="application/json"
        )
        return True
    except Exception:
        return False


def load_user_profile(sub: str) -> dict[str, Any] | None:
    try:
        blob = _bucket().blob(f"users/{sub}/profile.json")
        return json.loads(blob.download_as_text()) if blob.exists() else None
    except Exception:
        return None


def list_user_subs() -> list[str]:
    """Distinct user ids that own at least one run (users/{sub}/... prefixes)."""
    try:
        it = _cache_client().list_blobs(BUCKET, prefix="users/", delimiter=None)
        subs = set()
        for blob in it:
            parts = blob.name.split("/")
            if len(parts) >= _USER_PATH_PARTS:
                subs.add(parts[1])
        return sorted(subs)
    except Exception:
        return []


def _cache_client():
    if "client" not in _cache:
        from google.cloud import storage as gcs

        _cache["client"] = gcs.Client()
    return _cache["client"]


def delete_user_run(sub: str, run_id: str) -> bool:
    """Owner-scoped delete: the stub must live under this user's prefix, then the
    record and script go too. Deleting someone else's run is structurally impossible."""
    try:
        stub = _bucket().blob(f"users/{sub}/runs/{run_id}.json")
        if not stub.exists():
            return False
        stub.delete()
        for path in (f"records/{run_id}.json", f"scripts/{run_id}.fountain"):
            blob = _bucket().blob(path)
            if blob.exists():
                blob.delete()
        return True
    except Exception:
        return False

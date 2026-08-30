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

# Application-layer encryption: screenplays and full analysis records are
# encrypted BEFORE they reach the bucket (AES-128-CBC + HMAC via Fernet), so
# bucket access alone yields ciphertext. GCS's own at-rest encryption sits
# underneath. The key lives in the service environment, never in the bucket.
# Absent key -> plaintext (local dev, tests); legacy plaintext objects load.

_cache: dict = {}


def _fernet():
    if "fernet" not in _cache:
        key = os.getenv("ENCRYPTION_KEY", "")
        if not key:
            _cache["fernet"] = None
        else:
            from cryptography.fernet import Fernet

            _cache["fernet"] = Fernet(key.encode())
    return _cache["fernet"]


def _seal(plaintext: bytes) -> bytes:
    f = _fernet()
    return f.encrypt(plaintext) if f else plaintext


def _unseal(data: bytes) -> bytes:
    f = _fernet()
    if f is None:
        return data
    from cryptography.fernet import InvalidToken

    try:
        return f.decrypt(data)
    except InvalidToken:
        return data  # legacy plaintext object from before encryption


def _bucket():
    if "client" not in _cache:
        from google.cloud import storage as gcs

        _cache["client"] = gcs.Client()
    return _cache["client"].bucket(BUCKET)


def available() -> bool:
    """Whether durable storage is reachable at all.

    When it is not (local dev, tests, no credentials) nothing was ever
    persisted, so no run can carry an owner and the capability model is the
    only model — returning "no owner" there is correct, not a failure. That is
    a different fact from a configured bucket erroring on one read, which must
    never be read as "anonymous". Only success is cached, so a bucket that is
    briefly unreachable at boot does not disable ownership for the process.
    """
    if _cache.get("available"):
        return True
    try:
        _bucket()
    except Exception:
        return False
    _cache["available"] = True
    return True


def save_record(run_id: str, record: dict[str, Any]) -> bool:
    try:
        _bucket().blob(f"records/{run_id}.json").upload_from_string(
            _seal(json.dumps(record).encode()), content_type="application/octet-stream"
        )
        return True
    except Exception:
        return False


def save_pdf(run_id: str, kind: str, pdf: bytes) -> bool:
    """Write-once PDF artifacts (binder/one-sheet), sealed like the record —
    generated at run completion so downloads never cost web-tier CPU."""
    try:
        _bucket().blob(f"pdfs/{run_id}.{kind}.pdf").upload_from_string(
            _seal(pdf), content_type="application/octet-stream"
        )
        return True
    except Exception:
        return False


def load_pdf(run_id: str, kind: str) -> bytes | None:
    try:
        blob = _bucket().blob(f"pdfs/{run_id}.{kind}.pdf")
        return _unseal(blob.download_as_bytes()) if blob.exists() else None
    except Exception:
        return None


def load_record(run_id: str) -> dict[str, Any] | None:
    try:
        blob = _bucket().blob(f"records/{run_id}.json")
        if not blob.exists():
            return None
        return json.loads(_unseal(blob.download_as_bytes()))
    except Exception:
        return None


def save_script(run_id: str, source: str) -> bool:
    try:
        _bucket().blob(f"scripts/{run_id}.fountain").upload_from_string(
            _seal(source.encode()), content_type="application/octet-stream"
        )
        return True
    except Exception:
        return False


def load_script(run_id: str) -> str | None:
    try:
        blob = _bucket().blob(f"scripts/{run_id}.fountain")
        if not blob.exists():
            return None
        return _unseal(blob.download_as_bytes()).decode()
    except Exception:
        return None


RESEARCH_TTL_S = 7 * 24 * 3600  # a week: fresh enough for citations, stable for reruns


def load_research(key: str, max_age_s: float | None = RESEARCH_TTL_S) -> dict[str, Any] | None:
    """Cross-run research cache: the same clearance question re-asks the web at
    most weekly. Stabilizes reruns (same sources -> same verifier outcomes) and
    stops paying twice for the same question.

    max_age_s=None means "never expires" and is REQUIRED for the control-plane
    values that share this blob layer — the operator kill switch and invite
    redemptions are durable state, not cached research. Under the default TTL a
    paused service silently resumed itself a week later, and redeemed invites
    lapsed weekly; neither has anything to do with citation freshness.
    """
    try:
        blob = _bucket().blob(f"research/{key}.json")
        if not blob.exists():
            return None
        data = json.loads(blob.download_as_text())
        import time as _t

        if max_age_s is not None and _t.time() - data.get("_cached_at", 0) > max_age_s:
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


def save_owner(run_id: str, sub: str) -> bool:
    """Ownership marker, separate from the record so API responses never carry
    the Google subject id. Its absence means the run is anonymous."""
    try:
        _bucket().blob(f"owners/{run_id}").upload_from_string(sub, content_type="text/plain")
        return True
    except Exception:
        return False


class OwnerLookupError(RuntimeError):
    """The owner blob could not be READ. Distinct from "there is no owner":
    callers gate authorization on this answer, so a lookup failure must fail
    CLOSED (deny) instead of degrading into "anonymous, allowed"."""


def load_owner(run_id: str) -> str | None:
    """The run's owner sub, or None when the run is genuinely anonymous.

    Raises OwnerLookupError if the answer is unknown — never conflate a storage
    fault with an absent owner, because both ownership gates read a falsy
    result as "anonymous, anyone may act".
    """
    if not available():
        return None
    try:
        blob = _bucket().blob(f"owners/{run_id}")
        if not blob.exists():
            return None
        return blob.download_as_bytes().decode().strip()
    except Exception as e:
        raise OwnerLookupError(f"owner lookup failed for {run_id}: {type(e).__name__}") from e


def delete_anon_run(run_id: str) -> bool:
    """Capability delete for anonymous runs: the unguessable run id IS the
    authorization. The server refuses to route owned runs here."""
    try:
        deleted = False
        for path in (
            f"records/{run_id}.json",
            f"scripts/{run_id}.fountain",
            f"owners/{run_id}",
            f"pdfs/{run_id}.binder.pdf",
            f"pdfs/{run_id}.onesheet.pdf",
        ):
            blob = _bucket().blob(path)
            if blob.exists():
                blob.delete()
                deleted = True
        return deleted
    except Exception:
        return False


def delete_user_run(sub: str, run_id: str) -> bool:
    """Owner-scoped delete: the stub must live under this user's prefix, then the
    record and script go too. Deleting someone else's run is structurally impossible."""
    try:
        stub = _bucket().blob(f"users/{sub}/runs/{run_id}.json")
        if not stub.exists():
            return False
        stub.delete()
        for path in (
            f"records/{run_id}.json",
            f"scripts/{run_id}.fountain",
            f"owners/{run_id}",
            f"pdfs/{run_id}.binder.pdf",
            f"pdfs/{run_id}.onesheet.pdf",
        ):
            blob = _bucket().blob(path)
            if blob.exists():
                blob.delete()
        return True
    except Exception:
        return False

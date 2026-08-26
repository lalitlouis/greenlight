"""Clearance-run worker (ADR-1 Phase 2): `python -m greenlight.worker <run_id>`.

Runs one analysis to completion inside a Cloud Run Job execution. Shares
nothing with the web tier: the script comes from GCS, events go to the
Firestore journal, the record goes back to GCS. Deploying the web service
can never kill a run again — jobs run to completion on their own revision.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any

from greenlight import runstate, storage


class JournalPublisher:
    """Buffers structured events and flushes them to the Firestore journal in
    chunks — same cadence contract as the web tier's durable publisher."""

    def __init__(self, run_id: str, flush_every: float = 1.5, max_buffer: int = 40):
        self.run_id = run_id
        self.flush_every = flush_every
        self.max_buffer = max_buffer
        self._pending: list[dict[str, Any]] = []
        self._seq = 0
        self._last_flush = time.monotonic()

    def __call__(self, event: dict[str, Any]) -> None:
        if event.get("type") == "result":
            return  # records live in GCS, not the journal
        self._pending.append(event)
        now = time.monotonic()
        if len(self._pending) >= self.max_buffer or now - self._last_flush >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        batch, self._pending = self._pending, []
        runstate.events_append(self.run_id, self._seq, batch)
        self._seq += len(batch)
        self._last_flush = time.monotonic()


def _stub(run_id: str, record: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    rep = record.get("report") or {}
    return {
        "run_id": run_id,
        "kind": "clearance",
        "title": record.get("script_title") or state.get("title") or run_id,
        "status": "error" if record.get("error") else "done",
        "score": rep.get("greenlight_score"),
        "flags": len(record.get("flags", [])),
        "generated_at": record.get("generated_at"),
    }


def main() -> int:
    argc_needed = 2  # program name + run id
    run_id = sys.argv[1] if len(sys.argv) >= argc_needed else os.getenv("RUN_ID", "")
    if not run_id:
        print("usage: python -m greenlight.worker <run_id>  (or RUN_ID env)", file=sys.stderr)
        return 2
    state = runstate.run_get(run_id) or {}
    source = storage.load_script(run_id)
    if source is None:
        runstate.run_set(run_id, {"status": "error", "message": "script not found in storage"})
        print(f"worker: no script for {run_id}", file=sys.stderr)
        return 1

    workdir = Path("/tmp/greenlight-worker")
    workdir.mkdir(parents=True, exist_ok=True)
    script_path = workdir / f"{run_id}.fountain"
    script_path.write_text(source)

    publish = JournalPublisher(run_id)
    from greenlight import pipeline  # heavyweight import, after the cheap failures

    try:
        record = asyncio.run(pipeline.run(script_path, on_event=publish))
    except Exception as e:  # pipeline.run salvages internally; this is belt+braces
        publish.flush()
        runstate.run_set(run_id, {"status": "error", "message": f"{type(e).__name__}"})
        print(f"worker: run failed hard: {type(e).__name__}", file=sys.stderr)
        return 1
    publish.flush()
    record.pop("script_path", None)  # a worker-local path is meaningless elsewhere

    storage.save_record(run_id, record)
    status = "error" if record.get("error") else "done"
    owner = state.get("owner") or ""
    if owner:
        storage.save_owner(run_id, owner)
        storage.save_user_run(owner, run_id, _stub(run_id, record, state))
    runstate.run_set(run_id, {"status": status, "record_saved": True})
    runstate.increment("runs_completed")
    print(f"worker: {run_id} {status} ({record.get('elapsed_s')}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

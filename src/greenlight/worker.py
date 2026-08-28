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


def _publish_pdfs(run_id: str, record: dict) -> None:
    """Binder + one-sheet rendered ONCE here, at completion, cached in GCS —
    downloads become file reads instead of web-tier reportlab CPU. Non-fatal:
    the routes fall back to on-demand rendering for anything missing."""
    try:
        from greenlight import binder as binder_mod
        from greenlight import parser, pdfgen

        source = storage.load_script(run_id)
        scene_meta: dict = {}
        if source:
            _, scenes = parser.parse_fountain(source)
            scene_meta = {
                s["scene_id"]: {"heading": s["heading"], "page": s["page"]} for s in scenes
            }
        storage.save_pdf(run_id, "binder", pdfgen.binder_pdf(binder_mod.build(record, scene_meta)))
        storage.save_pdf(run_id, "onesheet", pdfgen.onesheet_pdf(record))
    except Exception as e:
        print(f"worker: pdf pre-render skipped: {type(e).__name__}", file=sys.stderr)


def _stub(run_id: str, record: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    rep = record.get("report") or {}
    return {
        "id": run_id,  # my.js keys every link off "id" — "run_id" broke report links
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
        record = asyncio.run(
            pipeline.run(
                script_path,
                on_event=publish,
                title_hint=state.get("title"),
                source_context=state.get("source_context"),
            )
        )
    except Exception as e:  # pipeline.run salvages internally; this is belt+braces
        publish.flush()
        runstate.run_set(run_id, {"status": "error", "message": f"{type(e).__name__}"})
        print(f"worker: run failed hard: {type(e).__name__}", file=sys.stderr)
        return 1
    publish.flush()
    record.pop("script_path", None)  # a worker-local path is meaningless elsewhere

    prev_id = state.get("previous_run_id") or ""
    if prev_id and not record.get("error"):
        prev = storage.load_record(prev_id)
        if prev:
            from greenlight.revision import diff_records

            try:
                record["revision"] = {
                    "of": prev_id,
                    "of_title": prev.get("script_title", ""),
                    "diff": diff_records(prev, record),
                }
            except Exception as e:  # a broken diff must never kill a paid run
                print(f"WARNING revision_diff_failed run={run_id}: {type(e).__name__}", flush=True)

    if not storage.save_record(run_id, record) and not storage.save_record(run_id, record):
        # the report would silently die with this instance — say so where alerting can see it
        print(f"ERROR record_save_failed run={run_id} — report persists only in memory", flush=True)
    _publish_pdfs(run_id, record)
    status = "error" if record.get("error") else "done"
    owner = state.get("owner") or ""
    if owner:
        storage.save_owner(run_id, owner)
        storage.save_user_run(owner, run_id, _stub(run_id, record, state))
    runstate.run_set(run_id, {"status": status, "record_saved": True})
    runstate.increment("runs_completed")
    # Structured run summary — the one log line that powers duration/quality
    # monitoring. Deliberately carries NO title and no script-derived text.
    import json as _json

    budgets = pipeline.scaled_budgets(record.get("report", {}).get("page_count") or 1)
    left = record.get("research_budget_left") or {}
    summary = {
        "kind": "run_summary",
        "run_id": run_id,
        "status": status,
        "elapsed_s": record.get("elapsed_s"),
        "scenes": record.get("scenes"),
        "pages": record.get("report", {}).get("page_count"),
        "entities": len(record.get("entities", [])),
        "flags": len(record.get("flags", [])),
        "rejected": len(record.get("rejected_flags", [])),
        "score": record.get("report", {}).get("greenlight_score"),
        "searches_spent": sum(max(0, budgets.get(d, 0) - (left.get(d) or 0)) for d in budgets),
    }
    print(_json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())

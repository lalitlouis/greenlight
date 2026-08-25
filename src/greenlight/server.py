"""GREENLIGHT web app: upload -> live four-desk stream -> report -> marked-up script.

Two modes, one SSE contract:

- LIVE:   POST /api/runs starts pipeline.run in a task; structured events (see
          pipeline.structured_events) are broadcast to any number of SSE subscribers.
- REPLAY: GET /api/replay synthesizes the same event stream from the newest cached
          record in runs/, paced with jitter so the four desks visibly interleave and
          finish at different times after different numbers of calls. The demo video
          is recorded from replay, never live (docs/DEMO.md) — so replay is a real
          feature, not a debug switch, and the front end has exactly one code path.

No AI SDK is imported here. The pipeline (and with it google-adk) is imported lazily
inside the live-run task only, so replay and tests never touch agent machinery.
"""

from __future__ import annotations

import asyncio
import json
import random
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from greenlight import parser
from greenlight.pdf import screenplay_text

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "runs"
STATIC_DIR = ROOT / "web" / "static"

DESKS = ("clearance_counsel", "ratings_board", "safety_underwriter", "territory_censor")

# Replay pacing (seconds). The 60-250ms band is a demo requirement: fast enough to
# feel autonomous, slow enough that a viewer can read the tool calls streaming by.
_DELAY_DESK = (0.06, 0.25)
_DELAY_VERIFY = (0.03, 0.12)


@dataclass
class RunHandle:
    """One run (live or replay) held in memory. Multiple SSE clients may attach:
    history lets a late subscriber catch up before joining the live broadcast."""

    run_id: str
    mode: str  # "live" | "replay"
    status: str = "running"  # "running" | "done" | "error"
    source: str | None = None  # fountain text, for /api/script
    script_path: str | None = None
    record: dict[str, Any] | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    subscribers: list[asyncio.Queue] = field(default_factory=list)

    def publish(self, event: dict[str, Any]) -> None:
        self.history.append(event)
        for q in self.subscribers:
            q.put_nowait(event)


RUNS: dict[str, RunHandle] = {}

app = FastAPI(title="ScriptRisk")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def cache_control(request, call_next):
    """The site iterates fast; a stale cached app.js renders a page that never
    hydrates. Vendored libraries and fonts are immutable-ish and may cache for a
    day; our own JS/CSS/HTML must always revalidate (ETag makes that a cheap 304)."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/vendor/"):
        response.headers["Cache-Control"] = "public, max-age=86400"
    elif path.startswith("/static/") or path in PAGES:
        response.headers["Cache-Control"] = "no-cache"
    return response


PAGES = {
    "/": "landing.html",
    "/home": "home.html",
    "/writer": "writer.html",
    "/cases": "cases.html",
    "/how-it-works": "how-it-works.html",
    "/faq": "faq.html",
    "/contact": "contact.html",
    "/run": "run.html",
    "/report": "report.html",
    "/script": "script.html",
}


def _page(name: str):
    async def serve() -> FileResponse:
        return FileResponse(STATIC_DIR / name)

    return serve


for route, filename in PAGES.items():
    app.get(route)(_page(filename))


# ---------------------------------------------------------------- live runs


async def _run_live(handle: RunHandle, script_path: Path) -> None:
    """Drive the real pipeline, forwarding its structured events to subscribers.

    pipeline.run already salvages partial results on agent errors; this wrapper
    catches everything above that (bad env, import failure) so the SSE stream
    always terminates with either `result` or `error` — never silence.
    """
    try:
        from greenlight import pipeline  # heavyweight (google-adk) — import only here

        record = await pipeline.run(script_path, on_event=handle.publish)
        handle.record = record
        handle.status = "error" if record.get("error") else "done"
        if record.get("error"):
            handle.publish({"type": "error", "message": record["error"], "partial": True})
        handle.publish({"type": "result", "record": record})
    except Exception as e:
        handle.status = "error"
        handle.publish({"type": "error", "message": f"{type(e).__name__}: {e}", "partial": False})
    finally:
        for q in handle.subscribers:
            q.put_nowait(None)  # sentinel: stream over


@app.post("/api/runs")
async def create_run(screenplay: UploadFile) -> dict[str, str]:
    source = screenplay_text(screenplay.filename or "", await screenplay.read())
    run_id = uuid.uuid4().hex[:12]
    upload_dir = RUNS_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{run_id}.fountain"
    path.write_text(source)

    handle = RunHandle(run_id=run_id, mode="live", source=source, script_path=str(path))
    RUNS[run_id] = handle
    title = (screenplay.filename or "screenplay").rsplit(".", 1)[0]
    handle.publish({"type": "meta", "run_id": run_id, "mode": "live", "script_title": title})
    asyncio.get_running_loop().create_task(_run_live(handle, path))
    return {"run_id": run_id}


# ---------------------------------------------------------------- replay


def _latest_record() -> tuple[Path, dict[str, Any]]:
    candidates = sorted(RUNS_DIR.glob("run_*.json"))
    if not candidates:
        raise HTTPException(404, "No cached runs in runs/ — do `make run` first.")
    path = candidates[-1]
    return path, json.loads(path.read_text())


def _synth_desk_events(record: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Reconstruct a plausible per-desk tool-call trace from a finished record.

    The record does not store the raw event log, but every flag implies the calls
    that produced it (read the scene, research it, file it) and carries the real
    citations — so the replayed research lines show genuine source titles, not props.
    Per-desk order follows flag_id order, which is the order the desk filed them.
    """
    per_desk: dict[str, list[dict[str, Any]]] = {d: [] for d in DESKS}
    all_flags = list(record.get("flags", [])) + list(record.get("rejected_flags", []))
    all_flags.sort(key=lambda f: f["flag_id"])

    for f in all_flags:
        desk = f["agent"]
        if desk not in per_desk:
            continue
        ev = per_desk[desk]
        scene = f["scene_ids"][0] if f["scene_ids"] else "S001"
        ev.append(
            {"type": "tool_call", "agent": desk, "tool": "read_scene", "args": {"scene_id": scene}}
        )
        ev.append(
            {
                "type": "tool_result",
                "agent": desk,
                "tool": "read_scene",
                "brief": f"{scene} · {len(f['scene_ids'])} scene(s) in scope",
            }
        )
        citations = f.get("citations", [])
        for c in citations[:2]:
            ev.append(
                {
                    "type": "tool_call",
                    "agent": desk,
                    "tool": "research",
                    "args": {"objective": c.get("title", f["category"])[:110]},
                }
            )
            host = (c.get("url") or "").split("/")[2] if "//" in (c.get("url") or "") else ""
            ev.append(
                {
                    "type": "tool_result",
                    "agent": desk,
                    "tool": "research",
                    "brief": f"excerpt captured · {host}",
                }
            )
        ev.append(
            {
                "type": "tool_call",
                "agent": desk,
                "tool": "file_flag",
                "args": {
                    "severity": f["severity"],
                    "category": f["category"],
                    "scene_ids": ", ".join(f["scene_ids"]),
                },
            }
        )
        ev.append(
            {
                "type": "tool_result",
                "agent": desk,
                "tool": "file_flag",
                "brief": f"filed {f['flag_id']} · {len(citations)} citation(s)",
            }
        )

    for desk, questions in (record.get("open_questions") or {}).items():
        for q in questions:
            if desk in per_desk:
                per_desk[desk].append(
                    {
                        "type": "tool_call",
                        "agent": desk,
                        "tool": "note_open_question",
                        "args": {"note": q[:160]},
                    }
                )

    for desk, ev in per_desk.items():
        filed = sum(1 for e in ev if e["type"] == "tool_call" and e["tool"] == "file_flag")
        calls = sum(1 for e in ev if e["type"] == "tool_call")
        ev.append(
            {
                "type": "text",
                "agent": desk,
                "text": f"done — {filed} flags filed in {calls} tool calls",
            }
        )
    return per_desk


def _synth_events(record: dict[str, Any]) -> list[list[dict[str, Any]]]:
    """The full replay script as phases: [triage], [desks interleaved],
    [verification], [adjudicator]. Interleaving uses a seeded RNG so replays are
    reproducible; desks with fewer events simply run out sooner — the asymmetric
    finish is emergent, exactly like the live run."""
    triage = [
        {
            "type": "text",
            "agent": "triage",
            "text": f"{record.get('scenes', '?')} scenes parsed — reading for named entities",
        },
        {
            "type": "tool_result",
            "agent": "triage",
            "brief": f"{len(record.get('entities', []))} entities → per-desk worklists",
            "tool": "triage",
        },
    ]

    per_desk = _synth_desk_events(record)
    rng = random.Random(1976)  # seeded: same interleave every replay, stable tests
    interleaved: list[dict[str, Any]] = []
    live = {d: list(ev) for d, ev in per_desk.items() if ev}
    while live:
        desk = rng.choice(list(live))
        interleaved.append(live[desk].pop(0))
        if not live[desk]:
            del live[desk]

    rejected_ids = {f["flag_id"] for f in record.get("rejected_flags", [])}
    verification: list[dict[str, Any]] = []
    for fid, v in sorted((record.get("verdicts") or {}).items()):
        verdict = "REJECTED" if fid in rejected_ids else v.get("verdict", "SUPPORTED")
        verification.append(
            {
                "type": "tool_call",
                "agent": "verification_panel",
                "tool": "verify_flag",
                "args": {"flag_id": fid},
            }
        )
        verification.append(
            {
                "type": "tool_result",
                "agent": "verification_panel",
                "tool": "verify_flag",
                "brief": f"{fid} · {verdict} — {v.get('reason', '')[:140]}",
            }
        )

    adjudicator = [
        {"type": "text", "agent": "adjudicator", "text": note[:300]}
        for note in record.get("adjudication_notes", [])
    ]
    return [triage, interleaved, verification, adjudicator]


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def _replay_stream(
    handle: RunHandle, record: dict[str, Any], pace: float
) -> AsyncIterator[str]:
    """Yield the synthesized stream with jittered delays. pace scales all delays;
    pace=0 (tests) streams instantly through the identical code path."""
    jitter = random.Random()
    yield _sse(handle.history[0])  # meta
    bands = [_DELAY_DESK, _DELAY_DESK, _DELAY_VERIFY, _DELAY_DESK]
    for phase, band in zip(_synth_events(record), bands, strict=True):
        for event in phase:
            handle.history.append(event)
            yield _sse(event)
            if pace > 0:
                await asyncio.sleep(jitter.uniform(*band) * pace)
    handle.status = "done"
    yield _sse({"type": "result", "record": record})


@app.get("/api/replay")
async def replay(pace: float = 1.0, record: str = "") -> StreamingResponse:
    """Replay a cached run (newest by default) as SSE — same contract as live."""
    pace = min(max(pace, 0.0), 10.0)
    if record:
        rec = _disk_record(record)
        if rec is None:
            raise HTTPException(404, f"Unknown record {record!r}")
        path, record_obj = RUNS_DIR / f"{record}.json", rec
    else:
        path, record_obj = _latest_record()
    record = None
    run_id = f"replay-{uuid.uuid4().hex[:8]}"
    handle = RunHandle(
        run_id=run_id,
        mode="replay",
        record=record_obj,
        script_path=record_obj.get("script_path"),
    )
    RUNS[run_id] = handle
    handle.publish(
        {
            "type": "meta",
            "run_id": run_id,
            "mode": "replay",
            "record_id": path.stem,
            "script_title": record_obj.get("script_title", path.stem),
            "recorded_at": record_obj.get("generated_at"),
        }
    )
    return StreamingResponse(
        _replay_stream(handle, record_obj, pace),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------- writer's room


WRITER_RUNS: dict[str, dict[str, Any]] = {}  # id -> {"status", "record"}


async def _run_writer(run_id: str, path: Path) -> None:
    try:
        from greenlight.writer import pipeline as writer_pipeline

        record = await writer_pipeline.run(path)
        WRITER_RUNS[run_id] = {
            "status": "error" if record.get("error") else "done",
            "record": record,
        }
    except Exception as e:
        WRITER_RUNS[run_id] = {"status": "error", "record": None, "message": str(e)[:300]}


@app.post("/api/writer")
async def create_writer_run(screenplay: UploadFile) -> dict[str, str]:
    source = screenplay_text(screenplay.filename or "", await screenplay.read())
    run_id = "w" + uuid.uuid4().hex[:11]
    upload_dir = RUNS_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{run_id}.fountain"
    path.write_text(source)
    WRITER_RUNS[run_id] = {"status": "running", "record": None}
    asyncio.get_running_loop().create_task(_run_writer(run_id, path))
    return {"run_id": run_id}


def _disk_writer_record(run_id: str) -> dict[str, Any] | None:
    if not run_id.replace("_", "").replace("-", "").isalnum():
        return None
    if run_id == "latest":
        candidates = sorted(RUNS_DIR.glob("writer_*.json"))
        return json.loads(candidates[-1].read_text()) if candidates else None
    path = RUNS_DIR / f"{run_id}.json"
    return json.loads(path.read_text()) if path.exists() else None


@app.get("/api/writer/{run_id}")
async def writer_status(run_id: str) -> dict[str, Any]:
    """Poll target for the writer page: {status, record}. Memory first, then disk."""
    if run_id in WRITER_RUNS:
        return {"id": run_id, **WRITER_RUNS[run_id]}
    if (record := _disk_writer_record(run_id)) is not None:
        return {"id": run_id, "status": "done", "record": record}
    raise HTTPException(404, f"Unknown writer run {run_id!r}")


# ---------------------------------------------------------------- case studies


@app.get("/api/cases")
async def list_cases() -> list[dict[str, Any]]:
    """Published case studies: famous screenplays, our analysis, script text never
    shipped (see scripts/case_study.py for the stripping rules)."""
    out: list[dict[str, Any]] = []
    for path in sorted(RUNS_DIR.glob("case_*.json")):
        try:
            r = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        rep = r.get("report") or {}
        case = r.get("case") or {}
        out.append(
            {
                "id": path.stem,
                "title": case.get("title", r.get("script_title", path.stem)),
                "year": case.get("year"),
                "hook": case.get("hook", ""),
                "score": rep.get("greenlight_score"),
                "blockers": (rep.get("counts") or {}).get("BLOCKER", 0),
                "flags": len(r.get("flags", [])),
                "rejected": len(r.get("rejected_flags", [])),
                "predicted_rating": (rep.get("rating_prediction") or {}).get("predicted"),
                "target_rating": (rep.get("rating_prediction") or {}).get("target"),
            }
        )
    out.sort(key=lambda c: c.get("year") or 0)
    return out


# ---------------------------------------------------------------- run index


def _summarize(record: dict[str, Any], run_id: str, kind: str) -> dict[str, Any]:
    rep = record.get("report") or {}
    return {
        "id": run_id,
        "kind": kind,  # "recorded" (on disk) | "session" (this server's memory)
        "title": record.get("script_title", run_id),
        "generated_at": record.get("generated_at"),
        "score": rep.get("greenlight_score"),
        "flags": len(record.get("flags", [])),
        "rejected": len(record.get("rejected_flags", [])),
        "blockers": (rep.get("counts") or {}).get("BLOCKER", 0),
        "predicted_rating": (rep.get("rating_prediction") or {}).get("predicted"),
        "demo": run_id.endswith("_demo"),
    }


@app.get("/api/runs")
async def list_runs() -> list[dict[str, Any]]:
    """Every viewable analysis: cached records on disk plus finished in-memory
    sessions. Newest first — the home page renders straight from this."""
    out: list[dict[str, Any]] = []
    for path in RUNS_DIR.glob("run_*.json"):
        try:
            out.append(_summarize(json.loads(path.read_text()), path.stem, "recorded"))
        except (json.JSONDecodeError, OSError):
            continue  # a torn or foreign file must not take the home page down
    for run_id, handle in RUNS.items():
        if handle.record is not None and handle.mode == "live":
            out.append(_summarize(handle.record, run_id, "session"))
    out.sort(key=lambda r: r.get("generated_at") or "", reverse=True)
    return out


def _disk_record(run_id: str) -> dict[str, Any] | None:
    # run ids are our own file stems — refuse anything path-shaped.
    if not run_id.replace("_", "").replace("-", "").isalnum():
        return None
    if run_id == "latest":  # stable alias: pages deep-link a real example
        candidates = sorted(RUNS_DIR.glob("run_*.json"))
        return json.loads(candidates[-1].read_text()) if candidates else None
    path = RUNS_DIR / f"{run_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


@app.get("/api/records/{run_id}")
async def get_record(run_id: str) -> dict[str, Any]:
    """One record by id — memory first (live sessions), then disk (cached runs)."""
    handle = RUNS.get(run_id)
    if handle is not None and handle.record is not None:
        return {"id": run_id, "kind": "session", "record": handle.record}
    if (record := _disk_record(run_id)) is not None:
        return {"id": run_id, "kind": "recorded", "record": record}
    raise HTTPException(404, f"Unknown record {run_id!r}")


# ---------------------------------------------------------------- shared endpoints


def _handle_or_404(run_id: str) -> RunHandle:
    handle = RUNS.get(run_id)
    if handle is None:
        raise HTTPException(404, f"Unknown run {run_id!r}")
    return handle


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    """SSE stream for a live run. History first, then the live broadcast, so a
    client that connects mid-run still sees the whole story."""
    handle = _handle_or_404(run_id)

    async def stream() -> AsyncIterator[str]:
        queue: asyncio.Queue = asyncio.Queue()
        # Snapshot history BEFORE subscribing on the same loop: no gap, no dupes.
        snapshot = list(handle.history)
        finished = handle.status != "running"
        if not finished:
            handle.subscribers.append(queue)
        try:
            for event in snapshot:
                yield _sse(event)
            if finished:
                if handle.record is not None and (
                    not snapshot or snapshot[-1].get("type") != "result"
                ):
                    yield _sse({"type": "result", "record": handle.record})
                return
            while True:
                event = await queue.get()
                if event is None:
                    return
                yield _sse(event)
        finally:
            if queue in handle.subscribers:
                handle.subscribers.remove(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/runs/{run_id}")
async def run_record(run_id: str) -> dict[str, Any]:
    handle = _handle_or_404(run_id)
    return {"run_id": run_id, "mode": handle.mode, "status": handle.status, "record": handle.record}


@app.get("/api/script/{run_id}")
async def run_script(run_id: str) -> dict[str, Any]:
    """The fountain source plus parsed scenes: the marked-up script view anchors
    flags to raw_span char offsets, so the source must be byte-identical to what
    the parser saw — hence re-reading the original file, never a re-assembly."""
    handle = RUNS.get(run_id)
    if handle is None:
        disk = _disk_record(run_id)
        if disk is None:
            raise HTTPException(404, f"Unknown run {run_id!r}")
        handle = RunHandle(run_id=run_id, mode="recorded", script_path=disk.get("script_path"))
    source = handle.source
    if source is None and handle.script_path:
        path = Path(handle.script_path)
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            raise HTTPException(404, f"Script file missing: {handle.script_path}")
        source = path.read_text()
    if source is None:
        raise HTTPException(404, "No script source for this run")
    meta, scenes = parser.parse_fountain(source)
    return {"run_id": run_id, "title": meta.get("title", ""), "source": source, "scenes": scenes}

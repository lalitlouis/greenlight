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
import contextlib
import json
import logging
import os
import random
import signal
import time as _time_module
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from greenlight import auth, firstlook, fixer, langguard, parser, runstate, storage
from greenlight.pdf import screenplay_text

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "runs"
STATIC_DIR = ROOT / "web" / "static"

DESKS = ("clearance_counsel", "ratings_board", "safety_underwriter", "territory_censor")

# Replay pacing (seconds). The 60-250ms band is a demo requirement: fast enough to
# feel autonomous, slow enough that a viewer can read the tool calls streaming by.
_DELAY_DESK = (0.14, 0.5)
_DELAY_VERIFY = (0.06, 0.2)


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
    owner: str | None = None  # user sub when a signed-in user started it
    owner_info: dict[str, Any] | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    durable: bool = False  # live runs journal to Firestore; replays do not
    _pending: list[dict[str, Any]] = field(default_factory=list)
    _flushed_seq: int = 0
    _flusher: Any = None

    def publish(self, event: dict[str, Any]) -> None:
        self.history.append(event)
        for q in self.subscribers:
            q.put_nowait(event)
        if self.durable and event.get("type") != "result":  # records live in GCS
            self._pending.append(event)
            if self._flusher is None or self._flusher.done():
                self._flusher = asyncio.get_event_loop().create_task(self._flush_soon())

    async def _flush_soon(self) -> None:
        await asyncio.sleep(1.5)  # coalesce a burst into one journal chunk
        self.flush_events()

    def flush_events(self) -> None:
        if not self._pending:
            return
        batch, self._pending = self._pending, []
        first = self._flushed_seq
        self._flushed_seq += len(batch)
        asyncio.get_event_loop().run_in_executor(
            None, runstate.events_append, self.run_id, first, batch
        )


RUNS: dict[str, RunHandle] = {}


def _handle_sigterm(*_args: Any) -> None:
    """Cloud Run gives ~10s of grace: mark everything in flight as failed so no
    stub is stranded 'running' and pollers get a terminal state."""
    for rid, h in list(WRITER_RUNS.items()):
        if h.get("status") == "running":
            h["status"] = "error"
            h["message"] = "instance shut down mid-run"
            with contextlib.suppress(Exception):
                runstate.set_state(rid, {"status": "error", "message": "instance shut down"})
    for rid, handle in list(RUNS.items()):
        if handle.mode == "live" and handle.status == "running" and handle.owner:
            stub = _running_stub(rid, "clearance", rid, handle.owner_info or {})
            stub["status"] = "error"
            with contextlib.suppress(Exception):
                storage.save_user_run(handle.owner, rid, stub)
    _log("sigterm", in_flight=len(RUNS) + len(WRITER_RUNS))


signal.signal(signal.SIGTERM, _handle_sigterm)

app = FastAPI(title="ScriptRisk")
app.mount("/static/v-{version}", StaticFiles(directory=str(STATIC_DIR)), name="static_versioned")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/robots.txt", include_in_schema=False)
async def robots() -> FileResponse:
    headers = {"Cache-Control": "public, max-age=3600"}
    return FileResponse(STATIC_DIR / "robots.txt", media_type="text/plain", headers=headers)


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap() -> FileResponse:
    headers = {"Cache-Control": "public, max-age=3600"}
    return FileResponse(STATIC_DIR / "sitemap.xml", media_type="application/xml", headers=headers)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    # Browsers ask for this at the root regardless of <link> tags.
    headers = {"Cache-Control": "public, max-age=86400"}
    return FileResponse(STATIC_DIR / "favicon.ico", headers=headers)


@app.get("/apple-touch-icon.png", include_in_schema=False)
@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
async def touch_icon() -> FileResponse:
    headers = {"Cache-Control": "public, max-age=86400"}
    return FileResponse(STATIC_DIR / "apple-touch-icon.png", headers=headers)


@app.get("/static/v-" + "{rest:path}", include_in_schema=False)
async def versioned_static(rest: str) -> FileResponse:
    # "/static/v-<version>/path/to/file" -> serve the file; version is only a cache key.
    _, _, path = rest.partition("/")
    target = (STATIC_DIR / path).resolve()
    if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(target)


# ---------------------------------------------------------------- hardening

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # a feature screenplay is well under 1MB; PDFs a few
MAX_TRACKED_RUNS = 60  # in-memory handles trimmed oldest-first; storage keeps the rest
# a live run costs real money and minutes; queue-jumping is a 429. Tunable now
# that workers carry the load (ADR-1 Phase 2/3) — raise with quota, not hope.
MAX_CONCURRENT_LIVE = int(os.getenv("MAX_CONCURRENT_LIVE", "5"))
RUN_MODE = os.getenv("RUN_MODE", "inprocess")  # "worker" dispatches Cloud Run Jobs
WORKER_JOB = os.getenv("WORKER_JOB", "greenlight-worker")
RATE_LIMIT_PER_HOUR = 8  # expensive-endpoint starts per client IP
RATE_WINDOW_S = 3600
MAX_TRACKED_IPS = 10000
MAX_ID_LEN = 64

_rate: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def _check_rate(request: Request) -> None:
    """Cost control, not bot defense: analyses spend API credit, so each IP gets a
    reasonable hourly allowance and the service caps concurrent live pipelines."""
    import time as _time

    now = _time.time()
    ip = _client_ip(request)
    window = [ts for ts in _rate.get(ip, []) if now - ts < RATE_WINDOW_S]
    if len(window) >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            429, "Rate limit: that's a lot of screenplays in one hour. Try again later."
        )
    window.append(now)
    _rate[ip] = window
    if len(_rate) > MAX_TRACKED_IPS:  # forgotten IPs must not accumulate forever
        for stale in [k for k, v in _rate.items() if not v or now - v[-1] > RATE_WINDOW_S][
            : MAX_TRACKED_IPS // 2
        ]:
            _rate.pop(stale, None)

    running = sum(1 for h in RUNS.values() if h.mode == "live" and h.status == "running")
    running += sum(1 for h in WRITER_RUNS.values() if h.get("status") == "running")
    if RUN_MODE == "worker":
        # the cap must see the whole fleet, not this instance's memory
        running = max(running, _fleet_running())
    if running >= MAX_CONCURRENT_LIVE:
        raise HTTPException(
            429,
            "All analysis desks are busy right now — try again in a few minutes, "
            "or watch a recorded analysis meanwhile.",
        )


async def _read_upload(screenplay: UploadFile) -> bytes:
    data = await screenplay.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Screenplay too large — 5MB max.")
    if not data.strip():
        raise HTTPException(422, "That file looks empty.")
    return data


def _safe_id(run_id: str) -> str:
    """Run ids are ours (hex / our file stems). Anything else never reaches a
    storage path — belt for the GCS fallbacks, suspenders for the disk ones."""
    if (
        not run_id
        or len(run_id) > MAX_ID_LEN
        or not run_id.replace("_", "").replace("-", "").isalnum()
    ):
        raise HTTPException(404, "Unknown run.")
    return run_id


def _trim_tracked() -> None:
    while len(RUNS) > MAX_TRACKED_RUNS:
        oldest = next(iter(RUNS))
        RUNS.pop(oldest, None)
    while len(WRITER_RUNS) > MAX_TRACKED_RUNS:
        WRITER_RUNS.pop(next(iter(WRITER_RUNS)), None)


logger = logging.getLogger("scriptrisk")
logging.basicConfig(level=logging.INFO, format="%(message)s")

HTTP_ERROR_STATUS = 500
CLIENT_LOG_WINDOW_S = 60
CLIENT_LOG_PER_MIN = 30

_metrics = {"started_at": _time_module.time(), "runs": 0, "writer_runs": 0, "errors": 0, "fixes": 0}


from collections import deque  # noqa: E402

RECENT_LOGS: deque = deque(maxlen=300)


_bump_tasks: set = set()


def _bump(counter: str) -> None:
    """Count once, in two places: fast in-memory for the pulse, durable in
    Firestore for all-time totals. Never blocks, never raises."""
    _metrics[counter] = _metrics.get(counter, 0) + 1
    with contextlib.suppress(Exception):
        task = asyncio.get_running_loop().create_task(
            asyncio.to_thread(runstate.increment, counter)
        )
        _bump_tasks.add(task)
        task.add_done_callback(_bump_tasks.discard)


def _log(kind: str, **fields: Any) -> None:
    """One JSON line per event on stdout — Cloud Run ships stdout to Cloud
    Logging automatically, so this IS the logging system, no agent needed."""
    with contextlib.suppress(Exception):
        entry = {"ts": _time_module.strftime("%H:%M:%S"), "kind": kind, **fields}
        RECENT_LOGS.append(entry)
        logger.info(json.dumps(entry, default=str))


@app.middleware("http")
async def request_logging(request: Request, call_next):
    start = _time_module.time()
    try:
        response = await call_next(request)
    except Exception as e:
        _bump("errors")
        _log(
            "http_error",
            path=request.url.path,
            method=request.method,
            error=f"{type(e).__name__}: {e}",
            ip=_client_ip(request),
        )
        raise
    dur_ms = round((_time_module.time() - start) * 1000)
    if not request.url.path.startswith("/static"):
        if response.status_code >= HTTP_ERROR_STATUS:
            _bump("errors")
        _log(
            "http",
            path=request.url.path,
            method=request.method,
            status=response.status_code,
            ms=dur_ms,
            ip=_client_ip(request),
        )
    return response


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: https://*.googleusercontent.com; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://accounts.google.com",
    )
    return response


@app.middleware("http")
async def cache_control(request, call_next):
    """The site iterates fast; a stale cached app.js renders a page that never
    hydrates. Vendored libraries and fonts are immutable-ish and may cache for a
    day; our own JS/CSS/HTML must always revalidate (ETag makes that a cheap 304)."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/v-"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/static/vendor/"):
        response.headers["Cache-Control"] = "public, max-age=86400"
    elif path.startswith("/static/") or path in PAGES:
        response.headers["Cache-Control"] = "no-cache"
    return response


PAGES = {
    "/": "landing.html",
    "/home": "home.html",
    "/writer": "writer.html",
    "/cases": "cases.html",
    # per-case URLs resolve below with case-specific meta — long-tail SEO
    # ("reservoir dogs clearance analysis") plus a clean shareable link each
    "/my": "my.html",
    "/compare": "compare.html",
    "/how-it-works": "how-it-works.html",
    "/desks": "desks.html",
    "/signin": "signin.html",
    "/faq": "faq.html",
    "/contact": "contact.html",
    "/run": "run.html",
    "/report": "report.html",
    "/script": "script.html",
    "/onesheet": "onesheet.html",
    "/binder": "binder.html",
    "/terms": "terms.html",
    "/privacy": "privacy.html",
}


# Cloud Run sets K_REVISION per deploy; locally we fall back to process start time.
ASSET_VERSION = os.getenv("K_REVISION", str(int(_time_module.time())))


def _versioned_html(name: str) -> str:
    html = (STATIC_DIR / name).read_text()
    html = html.replace('href="/static/', f'href="/static/v-{ASSET_VERSION}/')
    html = html.replace('src="/static/', f'src="/static/v-{ASSET_VERSION}/')
    # theme boot runs before stylesheets paint (no parchment flash for dark
    # users); an external file because CSP script-src is 'self', no inline
    boot = f'<script src="/static/v-{ASSET_VERSION}/theme-boot.js"></script>'
    return html.replace("<head>", "<head>" + boot, 1)


def _page(name: str):
    async def serve() -> HTMLResponse:
        """Serve the page with version-stamped asset URLs: a new deploy gets new
        URLs, so a browser can never mix cached files from two revisions."""
        return HTMLResponse(_versioned_html(name))

    return serve


for route, filename in PAGES.items():
    app.get(route)(_page(filename))


# ---------------------------------------------------------------- auth


def _current_user(request: Request) -> dict[str, Any] | None:
    return auth.read_session(request.cookies.get(auth.SESSION_COOKIE))


def _redirect_uri(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return f"{proto}://{request.headers.get('host', request.url.netloc)}/auth/callback"


_profiled_subs: set[str] = set()


@app.get("/api/auth/status")
async def auth_status(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    if user and user["sub"] not in _profiled_subs:
        _profiled_subs.add(user["sub"])
        await asyncio.to_thread(
            storage.save_user_profile,
            user["sub"],
            {
                "email": user.get("email", ""),
                "name": user.get("name", ""),
                "last_seen": _time_module.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
        )
    return {
        "configured": auth.configured(),
        "is_admin": auth.is_admin(user),
        "user": {"email": user["email"], "name": user["name"], "picture": user.get("picture", "")}
        if user
        else None,
    }


@app.get("/auth/login")
async def auth_login(request: Request, next: str = "") -> RedirectResponse:
    if not auth.configured():
        raise HTTPException(503, "Sign-in is not configured yet.")
    resp = RedirectResponse(auth.login_url(_redirect_uri(request)))
    # same-site paths only — an absolute URL here would be an open redirect
    if next.startswith("/") and not next.startswith("//"):
        resp.set_cookie("gl_next", next, max_age=600, httponly=True, samesite="lax")
    return resp


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse:
    if not auth.configured() or not code or not auth.check_state(state):
        raise HTTPException(400, "Sign-in failed — please try again.")
    try:
        user = await asyncio.to_thread(auth.exchange_code, code, _redirect_uri(request))
    except Exception as e:
        raise HTTPException(400, f"Sign-in failed: {type(e).__name__}") from e
    dest = request.cookies.get("gl_next", "")
    if not dest.startswith("/") or dest.startswith("//"):
        dest = "/home"
    resp = RedirectResponse(dest)
    resp.delete_cookie("gl_next")
    resp.set_cookie(
        auth.SESSION_COOKIE,
        auth.make_session(user),
        max_age=auth.SESSION_TTL_S,
        httponly=True,
        secure=request.headers.get("x-forwarded-proto") == "https",
        samesite="lax",
    )
    return resp


@app.post("/auth/logout")
async def auth_logout() -> dict[str, bool]:

    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.SESSION_COOKIE)
    return resp


def _running_stub(run_id: str, kind: str, title: str, who: dict[str, Any]) -> dict[str, Any]:
    """Registered at start so a user who navigates away can find their way back."""
    return {
        "status": "running",
        "owner_email": who.get("email", ""),
        "owner_name": who.get("name", ""),
        "id": run_id,
        "kind": kind,
        "title": title,
        "generated_at": _time_module.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "score": None,
        "verdict": None,
        "flags": 0,
    }


def _stub_from_record(
    run_id: str, kind: str, record: dict[str, Any], who: dict[str, Any] | None = None
) -> dict[str, Any]:
    rep = record.get("report") or {}
    cov = record.get("coverage") or {}
    return {
        "status": "done",
        "owner_email": (who or {}).get("email", ""),
        "owner_name": (who or {}).get("name", ""),
        "id": run_id,
        "kind": kind,
        "title": record.get("script_title", run_id),
        "generated_at": record.get("generated_at"),
        "score": rep.get("greenlight_score"),
        "verdict": cov.get("verdict"),
        "flags": len(record.get("flags", [])),
    }


@app.get("/api/my/runs")
async def my_runs(request: Request) -> list[dict[str, Any]]:
    user = _current_user(request)
    if user is None:
        raise HTTPException(401, "Sign in to see your history.")
    runs = await asyncio.to_thread(storage.list_user_runs, user["sub"])

    def _confirm_live(rs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # A long feature-script run outlives any age heuristic. For stubs still
        # marked running, ask the runstate ledger for the truth: confirmed-live
        # rows render as running at any age; finished ones get their real status.
        for r in rs:
            if r.get("status") != "running":
                continue
            state = runstate.get_state(str(r.get("id") or "")) or {}
            actual = state.get("status")
            if actual == "running":
                r["live"] = True
            elif actual in ("done", "error"):
                r["status"] = actual
        return rs

    return await asyncio.to_thread(_confirm_live, runs)


@app.delete("/api/my/runs/{run_id}")
async def delete_my_run(run_id: str, request: Request) -> dict[str, bool]:
    user = _current_user(request)
    if user is None:
        raise HTTPException(401, "Sign in first.")
    run_id = _safe_id(run_id)
    ok = await asyncio.to_thread(storage.delete_user_run, user["sub"], run_id)
    if not ok:
        raise HTTPException(404, "Not one of your reports.")
    RUNS.pop(run_id, None)
    WRITER_RUNS.pop(run_id, None)
    return {"ok": True}


# ---------------------------------------------------------------- live runs


async def _run_live(handle: RunHandle, script_path: Path) -> None:
    """Drive the real pipeline, forwarding its structured events to subscribers.

    pipeline.run already salvages partial results on agent errors; this wrapper
    catches everything above that (bad env, import failure) so the SSE stream
    always terminates with either `result` or `error` — never silence.
    """
    try:
        from greenlight import pipeline  # heavyweight (google-adk) — import only here

        def _first_look_then_publish() -> None:
            data = firstlook.run_first_look(handle.run_id, handle.source or "")
            if data:
                handle.publish({"type": "first_look", "data": data})

        asyncio.get_event_loop().run_in_executor(None, _first_look_then_publish)
        record = await pipeline.run(
            script_path,
            on_event=handle.publish,
            title_hint=getattr(handle, "title_hint", None),
            source_context=getattr(handle, "source_context", None),
        )
        handle.record = record
        handle.status = "error" if record.get("error") else "done"
        handle.flush_events()
        await asyncio.to_thread(
            runstate.run_set, handle.run_id, {"status": handle.status, "record_saved": True}
        )
        await asyncio.to_thread(storage.save_record, handle.run_id, record)
        if handle.owner:
            await asyncio.to_thread(storage.save_owner, handle.run_id, handle.owner)
            await asyncio.to_thread(
                storage.save_user_run,
                handle.owner,
                handle.run_id,
                _stub_from_record(handle.run_id, "clearance", record, handle.owner_info),
            )
        if record.get("error"):
            handle.publish({"type": "error", "message": record["error"], "partial": True})
        handle.publish({"type": "result", "record": record})
    except Exception as e:
        handle.status = "error"
        handle.publish({"type": "error", "message": f"{type(e).__name__}: {e}", "partial": False})
        handle.flush_events()
        await asyncio.to_thread(runstate.run_set, handle.run_id, {"status": "error"})
        if handle.owner:
            stub = _running_stub(handle.run_id, "clearance", handle.run_id, handle.owner_info or {})
            stub["status"] = "error"
            await asyncio.to_thread(storage.save_user_run, handle.owner, handle.run_id, stub)
    finally:
        for q in handle.subscribers:
            q.put_nowait(None)  # sentinel: stream over


def _require_signin(request: Request) -> dict[str, Any]:
    """Uploads require a signed-in user. Demo replays, case studies, and report
    views stay public — only running an analysis is gated. When OAuth is not
    configured (local dev), the gate stands down rather than locking everyone out."""
    owner = _current_user(request)
    if owner is None and auth.configured():
        raise HTTPException(401, "Sign in with Google to analyze a screenplay.")
    return owner


@app.post("/api/runs")
async def create_run(
    screenplay: UploadFile, request: Request, source_context: str = Form("")
) -> dict[str, str]:
    _check_rate(request)
    source_context = (source_context or "").strip()[:2000]
    owner = _require_signin(request)
    source = screenplay_text(screenplay.filename or "", await _read_upload(screenplay))
    english_ok = langguard.probably_english(source)
    if not english_ok:
        _log("non_english_upload", pages=len(source) // 3200)
    _trim_tracked()
    run_id = uuid.uuid4().hex[:12]
    upload_dir = RUNS_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{run_id}.fountain"
    path.write_text(source)

    handle = RunHandle(
        run_id=run_id,
        mode="live",
        source=source,
        script_path=str(path),
        owner=owner["sub"] if owner else None,
        owner_info=owner,
        durable=True,
    )
    RUNS[run_id] = handle
    await asyncio.to_thread(storage.save_script, run_id, source)
    title = (screenplay.filename or "screenplay").rsplit(".", 1)[0]
    title = title.replace("-", " ").replace("_", " ").strip().title() or "Screenplay"
    handle.title_hint = title
    handle.source_context = source_context
    await asyncio.to_thread(
        runstate.run_set,
        run_id,
        {
            "status": "running",
            "owner": owner["sub"] if owner else "",
            "title": title,
            "started_at": _time_module.time(),
            "english_ok": english_ok,
            "source_context": source_context,
        },
    )
    if RUN_MODE == "worker":
        RUNS.pop(run_id, None)  # the worker owns this run; no in-process shadow
        asyncio.get_event_loop().run_in_executor(None, firstlook.run_first_look, run_id, source)
        try:
            await asyncio.to_thread(_dispatch_worker, run_id)
        except Exception as e:
            await asyncio.to_thread(runstate.run_set, run_id, {"status": "error"})
            _log("worker_dispatch_failed", run_id=run_id, err=type(e).__name__)
            raise HTTPException(503, "Could not start the analysis worker — try again.") from e
        _bump("runs")
        pages = len(source) // 3200
        _log("run_started", run_id=run_id, pages=pages, owner=bool(owner), via="worker")
        if owner:
            await asyncio.to_thread(
                storage.save_user_run,
                owner["sub"],
                run_id,
                _running_stub(run_id, "clearance", title, owner),
            )
        return {"run_id": run_id}
    _bump("runs")
    # no title in logs: a screenplay's name is the user's content, and the
    # privacy page promises log lines carry no screenplay text
    _log("run_started", run_id=run_id, pages=len(source) // 3200, owner=bool(owner))
    if owner:
        await asyncio.to_thread(
            storage.save_user_run,
            owner["sub"],
            run_id,
            _running_stub(run_id, "clearance", title, owner),
        )
    handle.publish(
        {
            "type": "meta",
            "run_id": run_id,
            "mode": "live",
            "script_title": title,
            "started_at": _time_module.time(),
            "english_ok": english_ok,
        }
    )
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
        record = _safe_id(record)
        rec = await _load_record_any(record)  # disk, memory, or GCS — replays anywhere
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
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------- writer's room


WRITER_RUNS: dict[str, dict[str, Any]] = {}  # id -> {"status", "record"}


async def _run_writer(run_id: str, path: Path, owner: dict[str, Any] | None = None) -> None:
    def on_stage(name: str, info: dict[str, Any]) -> None:
        handle = WRITER_RUNS.get(run_id)
        if handle is not None:
            handle["stage"] = name
            handle["stage_info"] = info
            handle.setdefault("stages", {})[name] = info  # fast stages outlive the poll gap
            runstate.set_state(
                run_id, {"status": "running", "stage": name, "stages": handle["stages"]}
            )

    try:
        from greenlight.writer import pipeline as writer_pipeline

        record = await writer_pipeline.run(path, on_stage=on_stage)
        await asyncio.to_thread(storage.save_record, run_id, record)
        await asyncio.to_thread(
            runstate.set_state, run_id, {"status": "error" if record.get("error") else "done"}
        )
        if owner:
            await asyncio.to_thread(storage.save_owner, run_id, owner["sub"])
            await asyncio.to_thread(
                storage.save_user_run,
                owner["sub"],
                run_id,
                _stub_from_record(run_id, "writer", record, owner),
            )
        WRITER_RUNS[run_id] = {
            "status": "error" if record.get("error") else "done",
            "record": record,
        }
    except Exception as e:
        WRITER_RUNS[run_id] = {"status": "error", "record": None, "message": str(e)[:300]}
        await asyncio.to_thread(
            runstate.set_state, run_id, {"status": "error", "message": str(e)[:200]}
        )
        if owner:
            stub = _running_stub(run_id, "writer", run_id, owner)
            stub["status"] = "error"
            await asyncio.to_thread(storage.save_user_run, owner["sub"], run_id, stub)


@app.post("/api/writer")
async def create_writer_run(screenplay: UploadFile, request: Request) -> dict[str, str]:
    _check_rate(request)
    owner = _require_signin(request)
    source = screenplay_text(screenplay.filename or "", await _read_upload(screenplay))
    _trim_tracked()
    run_id = "w" + uuid.uuid4().hex[:11]
    upload_dir = RUNS_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{run_id}.fountain"
    path.write_text(source)
    _bump("writer_runs")
    _log("writer_started", run_id=run_id, owner=bool(owner))
    if owner:
        w_title = (screenplay.filename or "screenplay").rsplit(".", 1)[0]
        await asyncio.to_thread(
            storage.save_user_run,
            owner["sub"],
            run_id,
            _running_stub(run_id, "writer", w_title, owner),
        )
    WRITER_RUNS[run_id] = {"status": "running", "record": None, "stage": "upload", "stage_info": {}}
    asyncio.get_running_loop().create_task(_run_writer(run_id, path, owner))
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
    run_id = _safe_id(run_id)
    if run_id in WRITER_RUNS:
        return {"id": run_id, **WRITER_RUNS[run_id]}
    if (record := _disk_writer_record(run_id)) is not None:
        return {"id": run_id, "status": "done", "record": record}
    if (record := await asyncio.to_thread(storage.load_record, run_id)) is not None:
        return {"id": run_id, "status": "done", "record": record}
    # Cross-instance / post-restart: durable status while a run is in flight.
    if (state := await asyncio.to_thread(runstate.get_state, run_id)) is not None:
        return {"id": run_id, "record": None, **state}
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


# ---------------------------------------------------------------- admin


def _require_admin(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    if not auth.is_admin(user):
        # 404, not 403: the admin surface shouldn't advertise its existence.
        raise HTTPException(404, "Not found")
    return user


@app.get("/admin")
async def admin_page(request: Request) -> HTMLResponse:
    user = _current_user(request)
    if user is None and auth.configured():
        return RedirectResponse("/auth/login")
    _require_admin(request)
    html = (STATIC_DIR / "admin.html").read_text()
    html = html.replace('href="/static/', f'href="/static/v-{ASSET_VERSION}/')
    html = html.replace('src="/static/', f'src="/static/v-{ASSET_VERSION}/')
    return HTMLResponse(html)


@app.get("/api/admin/overview")
async def admin_overview(request: Request) -> dict[str, Any]:
    _require_admin(request)
    live_runs = [
        {"id": rid, "status": h.status, "mode": h.mode, "owner": bool(h.owner)}
        for rid, h in RUNS.items()
        if h.mode == "live"
    ]
    writer_live = [
        {"id": rid, "status": h.get("status"), "stage": h.get("stage")}
        for rid, h in WRITER_RUNS.items()
    ]

    def _roster() -> list[dict[str, Any]]:
        users = []
        for sub in storage.list_user_subs()[:100]:
            stubs = storage.list_user_runs(sub)
            latest = stubs[0] if stubs else {}
            profile = storage.load_user_profile(sub) or {}
            users.append(
                {
                    "sub": sub[:10] + "…",
                    "email": profile.get("email") or latest.get("owner_email", ""),
                    "name": profile.get("name") or latest.get("owner_name", ""),
                    "runs": len(stubs),
                    "latest_title": latest.get("title", ""),
                    "latest_at": latest.get("generated_at", ""),
                }
            )
        users.sort(key=lambda u: u.get("latest_at") or "", reverse=True)
        return users

    return {
        "metrics": {
            **_metrics,
            "uptime_s": round(_time_module.time() - _metrics["started_at"]),
            "asset_version": ASSET_VERSION,
        },
        "lifetime": await asyncio.to_thread(runstate.get_counters),
        "live": {"clearance": live_runs, "writer": writer_live},
        "logs": list(RECENT_LOGS)[-150:][::-1],
        "users": await asyncio.to_thread(_roster),
    }


# ---------------------------------------------------------------- client telemetry


class ClientLog(BaseModel):
    level: str = "info"
    event: str
    detail: str = ""
    page: str = ""


_client_log_rate: dict[str, list[float]] = {}


@app.post("/api/client-log")
async def client_log(body: ClientLog, request: Request) -> dict[str, bool]:
    """Browser beacons: page errors and stream milestones. This is how a 'stuck
    page' on someone else's machine becomes a log line on ours."""
    ip = _client_ip(request)
    now = _time_module.time()
    window = [ts for ts in _client_log_rate.get(ip, []) if now - ts < CLIENT_LOG_WINDOW_S]
    if len(window) >= CLIENT_LOG_PER_MIN:
        return {"ok": False}
    window.append(now)
    _client_log_rate[ip] = window
    if body.level == "error":
        _bump("errors")
    _log(
        "client",
        level=body.level[:10],
        event=body.event[:60],
        detail=body.detail[:300],
        page=body.page[:120],
        ip=ip,
        ua=request.headers.get("user-agent", "")[:120],
    )
    return {"ok": True}


@app.get("/api/metrics-lite")
async def metrics_lite() -> dict[str, Any]:
    running = sum(1 for h in RUNS.values() if h.mode == "live" and h.status == "running")
    running += sum(1 for h in WRITER_RUNS.values() if h.get("status") == "running")
    fleet = await asyncio.to_thread(_fleet_running)
    return {
        **_metrics,
        "uptime_s": round(_time_module.time() - _metrics["started_at"]),
        "tracked_runs": len(RUNS),
        "tracked_writer_runs": len(WRITER_RUNS),
        "running_now": max(running, fleet),
    }


# ---------------------------------------------------------------- fixes

FIX_RATE_PER_HOUR = 20
_fix_rate: dict[str, list[float]] = {}


class FixRequest(BaseModel):
    run_id: str
    flag_id: str


async def _load_record_any(run_id: str) -> dict[str, Any] | None:
    handle = RUNS.get(run_id)
    if handle is not None and handle.record is not None:
        return handle.record
    if (record := _disk_record(run_id)) is not None:
        return record
    return await asyncio.to_thread(storage.load_record, run_id)


async def _load_source_any(run_id: str, record: dict[str, Any]) -> str | None:
    handle = RUNS.get(run_id)
    if handle is not None and handle.source:
        return handle.source
    path_s = record.get("script_path")
    if path_s:
        path = Path(path_s)
        if not path.is_absolute():
            path = ROOT / path
        if path.exists():
            return path.read_text()
    return await asyncio.to_thread(storage.load_script, run_id)


WHATIF_RATE_PER_HOUR = 60
_whatif_rate: dict[str, list[float]] = {}


class WhatIfBody(BaseModel):
    run_id: str
    cuts: list[int]
    extra: list[str] = []


async def _binder_data(run_id: str) -> dict[str, Any]:
    run_id = _safe_id(run_id)
    record = await _load_record_any(run_id)
    if record is None:
        raise HTTPException(404, "Unknown run.")
    scene_meta: dict[str, dict[str, Any]] = {}
    source = await _load_source_any(run_id, record)
    if source:
        _, scenes = parser.parse_fountain(source)
        scene_meta = {s["scene_id"]: {"heading": s["heading"], "page": s["page"]} for s in scenes}
    from greenlight import binder as binder_mod

    return binder_mod.build(record, scene_meta)


@app.get("/api/binder/{run_id}.csv")
async def binder_csv(run_id: str) -> Response:
    """The same log as a CSV a legal team can file or import."""
    from greenlight import binder as binder_mod

    data = await _binder_data(run_id)
    fname = (data["title"] or "clearance-log").lower().replace(" ", "-")[:40]
    return Response(
        binder_mod.to_csv(data),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}-clearance-log.csv"'},
    )


CASE_SEO = {
    "reservoir-dogs": (
        "case_reservoir_dogs",
        "Reservoir Dogs — clearance & production-risk analysis | ScriptRisk",
        "What would Reservoir Dogs score today? Four AI clearance desks analyze the "
        "1992 screenplay — the needle-drops, the violence, the brands — every finding "
        "cited to the page.",
    ),
    "clerks": (
        "case_clerks",
        "Clerks — clearance & rating analysis of the NC-17 that became R | ScriptRisk",
        "Clerks drew an NC-17 purely for language, overturned on appeal. ScriptRisk "
        "calls the rating drivers from the page — cited, verified, priced.",
    ),
    "little-miss-sunshine": (
        "case_little_miss_sunshine",
        "Little Miss Sunshine — the family film with an R problem | ScriptRisk",
        "Super Freak, a minor on stage, and the language math: ScriptRisk analyzes the "
        "Little Miss Sunshine screenplay's clearance and rating exposure, cited to the page.",
    ),
    "the-social-network": (
        "case_the_social_network",
        "The Social Network — defamation, publicity & the biographical minefield | ScriptRisk",
        "Every character is a real person. ScriptRisk's clearance desks separate the "
        "documented record from dramatic invention across 47 cited findings — the "
        "biographical script stress test.",
    ),
    "the-wolf-of-wall-street": (
        "case_the_wolf_of_wall_street",
        "The Wolf of Wall Street — where docudrama meets actionable defamation | ScriptRisk",
        "Real people, real firms, real fraud on the page. 57 cited findings, "
        "USD 300k to 1.4M estimated clearance exposure, and the record-vs-invention line "
        "drawn scene by scene.",
    ),
    "the-hangover": (
        "case_the_hangover",
        "The Hangover — brands, casinos, stunts and a tiger, priced from the page | ScriptRisk",
        "A Vegas gauntlet of trademark, venue, and stunt exposure: ScriptRisk reads The "
        "Hangover the way a line producer's early-warning system would — cited and priced.",
    ),
}


@app.get("/cases/{slug}")
async def case_page(slug: str) -> HTMLResponse:
    """One URL per case study, with case-specific title/description/canonical.
    The page body is the report view for the case record."""
    entry = CASE_SEO.get(slug)
    if entry is None:
        raise HTTPException(404, "Unknown case study")
    record_id, title, desc = entry
    html = _versioned_html("report.html")
    # report.html is noindex by design (private per-run pages) — case studies
    # are the public, indexable exception
    html = html.replace('<meta name="robots" content="noindex">\n', "")
    html = html.replace('<meta name="robots" content="noindex">', "")
    html = html.replace(
        "<title>", f'<link rel="canonical" href="https://scriptrisk.com/cases/{slug}">\n<title>'
    )
    import re as _re

    html = _re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1)
    html = html.replace(
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta name="description" content="{desc}">',
        1,
    )
    # CSP forbids inline scripts (script-src 'self'), so the case's run id rides
    # a meta tag that report.js reads — the inline version was silently blocked.
    html = html.replace("</head>", f'<meta name="case-run-id" content="{record_id}"></head>', 1)
    return HTMLResponse(html)


@app.get("/api/binder/{run_id}.pdf")
async def binder_pdf_dl(run_id: str) -> Response:
    """The clearance log as a real PDF download — no print dialog."""
    from greenlight import pdfgen

    cached = await asyncio.to_thread(storage.load_pdf, _safe_id(run_id), "binder")
    if cached is not None:
        data = {"title": "clearance-log"}
        pdf = cached
        rec = await _load_record_any(_safe_id(run_id))
        fname = ((rec or {}).get("script_title") or "clearance-log").lower().replace(" ", "-")[:40]
        return Response(
            pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fname}-clearance-log.pdf"'},
        )
    data = await _binder_data(run_id)
    pdf = await asyncio.to_thread(pdfgen.binder_pdf, data)
    fname = (data["title"] or "clearance-log").lower().replace(" ", "-")[:40]
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}-clearance-log.pdf"'},
    )


@app.get("/api/onesheet/{run_id}.pdf")
async def onesheet_pdf_dl(run_id: str) -> Response:
    """The one-sheet poster as a real PDF download."""
    from greenlight import pdfgen

    run_id = _safe_id(run_id)
    record = await _load_record_any(run_id)
    if record is None:
        raise HTTPException(404, "Unknown run.")
    pdf = await asyncio.to_thread(storage.load_pdf, run_id, "onesheet")
    if pdf is None:
        pdf = await asyncio.to_thread(pdfgen.onesheet_pdf, record)
    fname = (record.get("script_title") or "one-sheet").lower().replace(" ", "-")[:40]
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}-one-sheet.pdf"'},
    )


@app.get("/api/binder/{run_id}")
async def binder_json(run_id: str) -> dict[str, Any]:
    """The clearance log as data — the /binder page renders from this."""
    return await _binder_data(run_id)


class ReviseBody(BaseModel):
    run_id: str
    format: str = "fountain"
    patches: list[dict[str, str]]


@app.post("/api/revise")
async def revise_script(body: ReviseBody, request: Request) -> Response:
    """Accepted fix patches applied to the source — download as Fountain with
    revision stars, or Final Draft .fdx with revision marks. Deterministic."""
    run_id = _safe_id(body.run_id)
    record = await _load_record_any(run_id)
    if record is None:
        raise HTTPException(404, "Unknown run.")
    if record.get("kind") == "case_study":
        raise HTTPException(400, "Case studies are read-only — their scripts are not stored.")
    source = await _load_source_any(run_id, record)
    if not source:
        raise HTTPException(404, "Script source unavailable for this run.")

    from greenlight import export as export_mod

    revised, applied, skipped = export_mod.apply_patches(source, body.patches)
    if not applied:
        raise HTTPException(400, "No patch applied cleanly: " + "; ".join(skipped[:4]))
    changed = export_mod.changed_lines(source, revised)
    title = record.get("script_title") or "screenplay"
    stem = title.lower().replace(" ", "-")[:40]
    _log(
        "revise_export", run_id=run_id, fmt=body.format, applied=len(applied), skipped=len(skipped)
    )
    if body.format == "fdx":
        return Response(
            export_mod.to_fdx(revised, changed, title),
            media_type="application/xml",
            headers={
                "Content-Disposition": f'attachment; filename="{stem}-revised.fdx"',
                "X-Patches-Applied": str(len(applied)),
                "X-Patches-Skipped": str(len(skipped)),
            },
        )
    return Response(
        export_mod.to_fountain(revised, changed),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{stem}-revised.fountain"',
            "X-Patches-Applied": str(len(applied)),
            "X-Patches-Skipped": str(len(skipped)),
        },
    )


@app.post("/api/whatif")
async def whatif_rating(body: WhatIfBody, request: Request) -> dict[str, Any]:
    """Projected rating with selected cut-list beats applied — the same
    profile -> embed -> comparables pipeline re-run on the revised rationale."""
    import time as _time

    ip = _client_ip(request)
    now = _time.time()
    window = [ts for ts in _whatif_rate.get(ip, []) if now - ts < RATE_WINDOW_S]
    if len(window) >= WHATIF_RATE_PER_HOUR:
        raise HTTPException(429, "What-if limit reached for this hour — try again later.")
    window.append(now)
    _whatif_rate[ip] = window

    run_id = _safe_id(body.run_id)
    record = await _load_record_any(run_id)
    if record is None:
        raise HTTPException(404, "Unknown run.")
    from greenlight import whatif as whatif_mod

    result = await asyncio.to_thread(
        whatif_mod.project, record, run_id, body.cuts[:12], body.extra[:4]
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    _log("whatif", run_id=run_id, cuts=len(body.cuts), projected=result.get("projected"))
    return result


@app.post("/api/whatif/suggest")
async def whatif_suggest(body: WhatIfBody, request: Request) -> dict[str, Any]:
    """More levers toward the target, grounded in the revised profile — each one
    comes back as a testable cut candidate, not advice."""
    import time as _time

    ip = _client_ip(request)
    now = _time.time()
    window = [ts for ts in _whatif_rate.get(ip, []) if now - ts < RATE_WINDOW_S]
    if len(window) >= WHATIF_RATE_PER_HOUR:
        raise HTTPException(429, "What-if limit reached for this hour — try again later.")
    window.append(now)
    _whatif_rate[ip] = window

    run_id = _safe_id(body.run_id)
    record = await _load_record_any(run_id)
    if record is None:
        raise HTTPException(404, "Unknown run.")
    from greenlight import whatif as whatif_mod

    result = await asyncio.to_thread(
        whatif_mod.suggest, record, run_id, body.cuts[:12], body.extra[:4]
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    _log("whatif_suggest", run_id=run_id, n=len(result.get("suggestions", [])))
    return result


@app.post("/api/fix")
async def propose_fix(body: FixRequest, request: Request) -> dict[str, Any]:
    """Draft minimal patches for one finding — the diff the report shows. Free
    during beta; this is the future paid surface, so it gets its own rate lane."""
    import time as _time

    ip = _client_ip(request)
    now = _time.time()
    window = [ts for ts in _fix_rate.get(ip, []) if now - ts < RATE_WINDOW_S]
    if len(window) >= FIX_RATE_PER_HOUR:
        raise HTTPException(429, "Fix limit reached for this hour — try again later.")
    window.append(now)
    _fix_rate[ip] = window

    run_id = _safe_id(body.run_id)
    record = await _load_record_any(run_id)
    if record is None:
        raise HTTPException(404, "Unknown run.")
    if record.get("kind") == "case_study":
        raise HTTPException(400, "Case studies are read-only — their scripts are not stored.")
    flag = next((f for f in record.get("flags", []) if f.get("flag_id") == body.flag_id), None)
    if flag is None:
        raise HTTPException(404, "Unknown finding.")
    source = await _load_source_any(run_id, record)
    if source is None:
        raise HTTPException(404, "Script source unavailable for this run.")

    _, scenes = parser.parse_fountain(source)
    by_id = {s["scene_id"]: s for s in scenes}
    scene_texts = {
        sid: source[by_id[sid]["raw_span"][0] : by_id[sid]["raw_span"][1]]
        for sid in flag.get("scene_ids", [])
        if sid in by_id
    }
    if not scene_texts:
        raise HTTPException(400, "The finding's scenes could not be located in the script.")

    _bump("fixes")
    _log("fix_requested", run_id=run_id, flag_id=body.flag_id)
    result = await fixer.propose_fix(flag, scene_texts)
    if "error" in result:
        raise HTTPException(502, result["error"])
    return result


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


# The records the home page shows. Update when the demo record is refreshed.
HOME_RECORDS = {"run_20260826_demo"}


@app.get("/api/runs")
async def list_runs() -> list[dict[str, Any]]:
    """Curated records only — the demo runs shipped in runs/. A visitor's own
    analysis is reachable solely through its unguessable run id (their link),
    or through My reports when signed in. Nobody browses anyone else's run."""
    out: list[dict[str, Any]] = []
    for path in RUNS_DIR.glob("run_*.json"):
        if path.stem not in HOME_RECORDS:
            continue  # dev-iteration records stay on disk for `make eval`, unlisted
        try:
            out.append(_summarize(json.loads(path.read_text()), path.stem, "recorded"))
        except (json.JSONDecodeError, OSError):
            continue  # a torn or foreign file must not take the home page down
    out.sort(key=lambda r: r.get("generated_at") or "", reverse=True)
    return out


@app.delete("/api/runs/{run_id}")
async def delete_run(run_id: str, request: Request) -> dict[str, bool]:
    """Delete one analysis. Owned runs require the owner's session; anonymous
    runs are deletable by anyone holding the unguessable id — the link is the
    capability. Curated demo records are refused outright."""
    run_id = _safe_id(run_id)
    if _disk_record(run_id) is not None:
        raise HTTPException(403, "Curated demo records cannot be deleted")
    owner = await asyncio.to_thread(storage.load_owner, run_id)
    if owner:
        user = _current_user(request)
        if not user or user["sub"] != owner:
            raise HTTPException(403, "This run belongs to a signed-in account")
        ok = await asyncio.to_thread(storage.delete_user_run, owner, run_id)
    else:
        ok = await asyncio.to_thread(storage.delete_anon_run, run_id)
        # a run still finishing lives only in memory — drop that too
        ok = RUNS.pop(run_id, None) is not None or ok
    if not ok:
        raise HTTPException(404, "No such run")
    if owner:
        RUNS.pop(run_id, None)
    _log("run_deleted", run_id=run_id, owned=bool(owner))
    return {"ok": True}


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
    run_id = _safe_id(run_id)
    handle = RUNS.get(run_id)
    if handle is not None and handle.record is not None:
        return {"id": run_id, "kind": "session", "record": handle.record}
    if handle is not None and handle.mode == "live":
        # still running: no record yet, but very much not unknown — the client
        # sends the viewer to the live stream instead of an error
        return {"id": run_id, "kind": "running", "status": handle.status}
    fleet_state = await asyncio.to_thread(runstate.run_get, run_id)
    if fleet_state is not None and fleet_state.get("status") == "running":
        return {"id": run_id, "kind": "running", "status": "running"}
    if (record := _disk_record(run_id)) is not None:
        return {"id": run_id, "kind": "recorded", "record": record}
    if (record := await asyncio.to_thread(storage.load_record, run_id)) is not None:
        return {"id": run_id, "kind": "stored", "record": record}
    raise HTTPException(404, f"Unknown record {run_id!r}")


# ---------------------------------------------------------------- shared endpoints


def _fleet_running() -> int:
    try:
        return runstate.count_running()
    except Exception:
        return 0


def _dispatch_worker(run_id: str) -> None:
    """Fire one Cloud Run Job execution for this run. Synchronous call to the
    Jobs API; the execution itself is fully detached from this process."""
    from google.cloud import run_v2

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    region = os.getenv("WORKER_REGION", "us-central1")
    client = run_v2.JobsClient()
    client.run_job(
        request=run_v2.RunJobRequest(
            name=f"projects/{project}/locations/{region}/jobs/{WORKER_JOB}",
            overrides=run_v2.RunJobRequest.Overrides(
                container_overrides=[
                    # overrides REPLACE the job's args entirely — carry the module too
                    run_v2.RunJobRequest.Overrides.ContainerOverride(
                        args=["-m", "greenlight.worker", run_id]
                    )
                ]
            ),
        )
    )


def _handle_or_404(run_id: str) -> RunHandle:
    handle = RUNS.get(run_id)
    if handle is None:
        raise HTTPException(404, f"Unknown run {run_id!r}")
    return handle


async def _journal_relay(run_id: str) -> AsyncIterator[str]:
    """Tail the Firestore journal for a run this process does not hold — a run
    on another instance, a worker job, or one that survived our restart. Same
    SSE contract; the client cannot tell the difference."""
    seq = -1
    idle = 0.0
    state0 = await asyncio.to_thread(runstate.run_get, run_id) or {}
    sent_first_look = False
    # the journal carries no meta event — synthesize the one the run page boots from
    yield _sse(
        {
            "type": "meta",
            "run_id": run_id,
            "mode": "live",
            "script_title": state0.get("title") or "Analysis",
            "started_at": state0.get("started_at"),
            "english_ok": state0.get("english_ok", True),
        }
    )
    while True:
        events, seq = await asyncio.to_thread(runstate.events_read, run_id, seq)
        for ev in events:
            yield _sse(ev)
        state = await asyncio.to_thread(runstate.run_get, run_id) or {}
        if not sent_first_look and state.get("first_look"):
            sent_first_look = True
            yield _sse({"type": "first_look", "data": state["first_look"]})
        if state.get("status") in ("done", "error"):
            # drain any final chunk that raced the status write
            events, seq = await asyncio.to_thread(runstate.events_read, run_id, seq)
            for ev in events:
                yield _sse(ev)
            record = await _load_record_any(run_id)
            if record is not None:
                yield _sse({"type": "result", "record": record})
            else:
                msg = {"type": "error", "message": "run ended; record unavailable", "partial": True}
                yield _sse(msg)
            return
        idle = min(idle + 0.25, 2.0) if not events else 0.5
        await asyncio.sleep(idle)


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    """SSE stream for a live run. History first, then the live broadcast, so a
    client that connects mid-run still sees the whole story."""
    handle = RUNS.get(run_id)
    if handle is None:
        # not in this process's memory — if the journal knows it, relay from there
        safe = _safe_id(run_id)
        state = await asyncio.to_thread(runstate.run_get, safe)
        if state is None:
            raise HTTPException(404, f"Unknown run {run_id!r}")
        return StreamingResponse(
            _journal_relay(safe),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

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
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
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
        run_id = _safe_id(run_id)
        disk = _disk_record(run_id)
        if disk is not None:
            handle = RunHandle(run_id=run_id, mode="recorded", script_path=disk.get("script_path"))
        else:
            stored = await asyncio.to_thread(storage.load_script, run_id)
            if stored is None:
                raise HTTPException(404, f"Unknown run {run_id!r}")
            handle = RunHandle(run_id=run_id, mode="stored", source=stored)
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
    from greenlight import profile as profile_mod

    return {
        "run_id": run_id,
        "title": meta.get("title", ""),
        "source": source,
        "scenes": scenes,
        "profile": profile_mod.build_profile(scenes),
    }

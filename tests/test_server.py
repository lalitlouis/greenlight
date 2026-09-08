"""Replay endpoints of the web server. No live agent runs, no network.

Replay is the demo path (docs/DEMO.md: the video is recorded from replay, never
live), so these tests pin the SSE contract the front end renders from: meta first,
per-desk tool_call traces, verification verdicts, and a terminal `result` event
carrying the full record. pace=0 streams instantly through the same code path.
"""

import json

import pytest
from fastapi.testclient import TestClient

from greenlight import server as _server_mod
from greenlight.server import DESKS, app

client = TestClient(app)

# captured at import, before the autouse _hermetic_pause fixture stubs it out —
# the kill-switch test needs the real implementation
_REAL_RUNS_PAUSED = _server_mod._runs_paused


@pytest.fixture(autouse=True)
def _hermetic_pause(monkeypatch):
    """Unit tests must never read the PRODUCTION pause flag: the owner flipping
    the live kill switch once turned two upload tests red (503) and blocked a
    deploy. Tests that exercise the pause monkeypatch it explicitly."""
    from greenlight import server

    monkeypatch.setattr(server, "_runs_paused", lambda: None)


def sse_events(response) -> list[dict]:
    """Decode a text/event-stream body into its JSON data payloads."""
    events = []
    for line in response.iter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


@pytest.fixture(scope="module")
def replay():
    """One replayed stream, shared: (events, record). Replay reads the newest
    runs/run_*.json, which is committed to the repo — no fixtures needed here."""
    with client.stream("GET", "/api/replay?pace=0") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = sse_events(response)
    result = events[-1]
    return events, result["record"]


def test_replay_stream_starts_with_meta_and_ends_with_result(replay):
    events, record = replay
    assert events[0]["type"] == "meta"
    assert events[0]["mode"] == "replay"
    assert events[0]["run_id"].startswith("replay-")
    assert events[-1]["type"] == "result"
    assert record["script_title"] == events[0]["script_title"]


def test_all_four_desks_emit_tool_calls(replay):
    events, _ = replay
    agents_calling = {e["agent"] for e in events if e.get("type") == "tool_call"}
    for desk in DESKS:
        assert desk in agents_calling


def test_desks_file_every_recorded_flag_and_finish_asymmetrically(replay):
    """The visual proof of autonomy: each desk files exactly its recorded flags
    (kept + rejected), and desks make different numbers of calls."""
    events, record = replay
    filed = {d: 0 for d in DESKS}
    calls = {d: 0 for d in DESKS}
    for e in events:
        if e.get("type") == "tool_call" and e["agent"] in filed:
            calls[e["agent"]] += 1
            if e["tool"] == "file_flag":
                filed[e["agent"]] += 1
    expected = {d: 0 for d in DESKS}
    for f in record["flags"] + record["rejected_flags"]:
        expected[f["agent"]] += 1
    assert filed == expected
    assert len(set(calls.values())) > 1  # not a lockstep progress bar


def test_verification_events_cover_rejections(replay):
    events, record = replay
    briefs = [e.get("brief", "") for e in events if e.get("agent") == "verification_panel"]
    for f in record["rejected_flags"]:
        assert any(f["flag_id"] in b and "REJECTED" in b for b in briefs)


def test_result_record_upholds_citation_invariant(replay):
    """A flag without a citation does not render — so it must never reach the UI."""
    _, record = replay
    assert record["flags"], "cached run has no flags; demo record is broken"
    for f in record["flags"]:
        assert f["citations"], f"{f['flag_id']} has no citations"
    for f in record["rejected_flags"]:
        assert f["rejection_reason"]


def test_record_endpoint_serves_replayed_run(replay):
    events, record = replay
    run_id = events[0]["run_id"]
    res = client.get(f"/api/runs/{run_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "done"
    assert body["record"]["script_title"] == record["script_title"]


def test_script_endpoint_anchors_scenes_to_source(replay):
    events, record = replay
    run_id = events[0]["run_id"]
    res = client.get(f"/api/script/{run_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["scenes"], "no scenes parsed"
    assert len(body["scenes"]) == record["scenes"]
    for scene in body["scenes"]:
        start, end = scene["raw_span"]
        chunk = body["source"][start:end]
        # raw_span slices the original source: the heading opens its own chunk.
        assert chunk.lstrip().startswith(scene["heading"])


def test_unknown_run_is_404():
    for path in ("/api/runs/nope", "/api/runs/nope/events", "/api/script/nope"):
        assert client.get(path).status_code == 404


def test_upload_without_file_is_422():
    assert client.post("/api/runs").status_code == 422


def test_index_serves_static_ui():
    res = client.get("/")
    assert res.status_code == 200
    assert "ScriptRisk" in res.text


def test_all_pages_serve():
    for route in [
        "/",
        "/home",
        "/how-it-works",
        "/faq",
        "/contact",
        "/run",
        "/report",
        "/script",
        "/compare",
        "/my",
    ]:
        res = client.get(route)
        assert res.status_code == 200, route
        assert "ScriptRisk" in res.text, route


def test_runs_index_lists_recorded_runs():
    res = client.get("/api/runs")
    assert res.status_code == 200
    runs = res.json()
    assert runs, "committed demo record should be listed"
    demo = [r for r in runs if r["demo"]]
    assert demo and demo[0]["score"] is not None and demo[0]["flags"] > 0
    assert runs == sorted(runs, key=lambda r: r.get("generated_at") or "", reverse=True)


def test_record_endpoint_serves_disk_records():
    run_id = client.get("/api/runs").json()[0]["id"]
    res = client.get(f"/api/records/{run_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "recorded"
    assert body["record"]["flags"]
    # path traversal shaped ids are refused, not resolved
    assert client.get("/api/records/..%2f..%2fetc").status_code == 404


def test_script_endpoint_works_for_disk_records():
    run_id = client.get("/api/runs").json()[0]["id"]
    res = client.get(f"/api/script/{run_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["scenes"] and data["source"]


def test_replay_accepts_record_selection(replay):
    run_id = client.get("/api/runs").json()[0]["id"]
    with client.stream("GET", f"/api/replay?pace=0&record={run_id}") as response:
        assert response.status_code == 200
        events = sse_events(response)
    assert events[0]["record_id"] == run_id
    assert events[-1]["type"] == "result"


def test_latest_alias_resolves_newest_record():
    res = client.get("/api/records/latest")
    assert res.status_code == 200 and res.json()["record"]["flags"]
    assert client.get("/api/script/latest").status_code == 200


def test_writer_page_and_latest_record():
    assert client.get("/writer").status_code == 200
    res = client.get("/api/writer/latest")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "done"
    assert body["record"]["coverage"]["verdict"] in {"PASS", "CONSIDER", "RECOMMEND"}
    assert body["record"]["format"]["checks"]
    assert body["record"]["pitch"]["comps"], "comps must be retrieved, and shipped in the demo"


def test_oversized_upload_rejected():
    res = client.post(
        "/api/runs", files={"screenplay": ("big.fountain", b"A" * (5 * 1024 * 1024 + 10))}
    )
    assert res.status_code == 413


def test_empty_upload_rejected():
    res = client.post("/api/writer", files={"screenplay": ("empty.fountain", b"   ")})
    assert res.status_code == 422


def test_hostile_run_ids_rejected_everywhere():
    for bad in ["..%2fetc", "a/b", "x" * 80, "run_1;drop"]:
        assert client.get(f"/api/records/{bad}").status_code == 404
        assert client.get(f"/api/writer/{bad}").status_code == 404
        assert client.get(f"/api/script/{bad}").status_code == 404


def test_security_headers_present():
    res = client.get("/")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in res.headers["Content-Security-Policy"]


def test_fix_rejects_case_studies_and_unknown_flags():
    res = client.post("/api/fix", json={"run_id": "case_clerks", "flag_id": "F101"})
    assert res.status_code == 400
    res = client.post("/api/fix", json={"run_id": "nonexistent_run", "flag_id": "F101"})
    assert res.status_code == 404


def test_replay_404s_cleanly_on_unknown_record():
    res = client.get("/api/replay?pace=0&record=doesnotexist123")
    assert res.status_code == 404


def test_admin_surface_hidden_from_anonymous():
    assert client.get("/api/admin/overview").status_code == 404
    # /admin redirects to sign-in when auth is configured, 404s when not
    res = client.get("/admin", follow_redirects=False)
    assert res.status_code in (404, 307)


# --- access control: kill switch + invite codes ------------------------------


def test_kill_switch_blocks_new_runs(monkeypatch):
    from greenlight import server

    monkeypatch.setattr(server, "_runs_paused", lambda: {"paused": True})
    r = client.post("/api/runs", files={"screenplay": ("t.fountain", b"INT. ROOM - DAY\n")})
    assert r.status_code == 503
    assert "paused" in r.json()["detail"].lower()


def test_pause_endpoints_are_admin_only():
    assert client.get("/api/admin/pause").status_code == 403
    assert client.post("/api/admin/pause", json={"paused": True}).status_code == 403


def test_invite_gate_blocks_unredeemed(monkeypatch):
    from greenlight import server

    monkeypatch.setattr(server, "REQUIRE_INVITE", True)
    monkeypatch.setattr(server.storage, "load_research", lambda k, max_age_s=None: None)
    r = client.post("/api/runs", files={"screenplay": ("t.fountain", b"INT. ROOM - DAY\n")})
    assert r.status_code == 403
    assert "invite" in r.json()["detail"].lower()


def test_invite_redeem_requires_signin():
    assert client.post("/api/invite", json={"code": "x"}).status_code == 401


def test_invite_redeemed_user_passes_gate(monkeypatch):
    from greenlight import server

    monkeypatch.setattr(server, "REQUIRE_INVITE", True)
    stored = {}

    def fake_save(k, v):
        stored[k] = v
        return True

    monkeypatch.setattr(server.storage, "load_research", lambda k, max_age_s=None: stored.get(k))
    monkeypatch.setattr(server.storage, "save_research", fake_save)
    monkeypatch.setattr(server, "_INVITE_CODES", {"PILOT1"})
    user = {"sub": "u1", "email": "pilot@example.com"}
    monkeypatch.setattr(server, "_current_user", lambda req: user)
    r = client.post("/api/invite", json={"code": "PILOT1"})
    assert r.status_code == 200
    # gate now passes for this user (invite:u1 stored)
    server._require_invite(user)  # must not raise


# --- observability: severity-tagged logs + fleet-wide admin runs -------------


def test_log_line_carries_severity_and_rfc3339_time(caplog):
    import logging

    from greenlight import server

    with caplog.at_level(logging.INFO, logger="scriptrisk"):
        server._log("unit_test_event", severity="ERROR", foo="bar")
    line = json.loads(caplog.records[-1].getMessage())
    assert line["severity"] == "ERROR"
    assert line["kind"] == "unit_test_event"
    assert line["foo"] == "bar"
    assert "T" in line["time"] and line["time"].endswith("Z")
    # the in-memory admin feed stays compact — no severity/time duplication
    assert "severity" not in server.RECENT_LOGS[-1]


def test_list_runs_degrades_without_firestore(monkeypatch):
    from greenlight import runstate

    monkeypatch.setitem(runstate._cache, "db", None)  # .collection raises -> []
    assert runstate.list_runs() == []


def test_admin_overview_fleet_reads_firestore_not_memory(monkeypatch):
    """The 'who is running what' table must come from the fleet-wide Firestore
    ledger — in worker mode the web tier drops its in-memory handle, so RUNS
    alone under-reports."""
    from greenlight import server

    monkeypatch.setattr(server.auth, "is_admin", lambda user: True)
    monkeypatch.setattr(server, "_current_user", lambda req: {"sub": "adm", "email": "a@b.c"})
    monkeypatch.setattr(server.runstate, "get_counters", lambda: {})
    monkeypatch.setattr(server.storage, "list_user_subs", lambda: [])
    now = server._time_module.time()
    monkeypatch.setattr(
        server.runstate,
        "list_runs",
        lambda limit=20: [
            {
                "id": "run_a",
                "status": "running",
                "title": "Live One",
                "owner": "subsubsubsub",
                "started_at": now - 60,
            },
            {"id": "run_b", "status": "done", "started_at": now - 600, "finished_at": now - 300},
            {"id": "run_c", "status": "error", "started_at": now - 9000},
        ],
    )
    o = client.get("/api/admin/overview").json()
    by_id = {r["id"]: r for r in o["fleet"]}
    assert 55 <= by_id["run_a"]["elapsed_s"] <= 65  # running: now - started_at
    assert by_id["run_b"]["elapsed_s"] == 300  # finished: finished_at - started_at
    assert by_id["run_c"]["elapsed_s"] is None  # pre-finished_at doc: unknowable
    assert by_id["run_a"]["owner"] == "subsubsubs…"  # sub truncated, no roster match


# --- security fixes (2026-08-30 security review) -----------------------------


def test_paid_endpoints_require_signin(monkeypatch):
    """/api/fix and the what-if pair spend model budget (fix uses the Pro tier).
    Anonymous callers could drive them against the PUBLIC demo run id, throttled
    only by a spoofable per-IP lane."""
    from greenlight import auth as auth_mod
    from greenlight import server

    monkeypatch.setattr(server, "_current_user", lambda req: None)
    monkeypatch.setattr(auth_mod, "configured", lambda: True)
    body = {"run_id": "run_20260902_demo", "cuts": [], "extra": []}
    assert client.post("/api/whatif", json=body).status_code == 401
    assert client.post("/api/whatif/suggest", json=body).status_code == 401
    assert (
        client.post("/api/fix", json={"run_id": "run_20260902_demo", "flag_id": "F101"}).status_code
        == 401
    )


def test_client_ip_ignores_the_spoofable_left_hop():
    """Cloud Run appends the real peer; the left of X-Forwarded-For is whatever
    the caller typed. Keying limits off it let one client mint a fresh bucket
    per request by rotating the header."""
    from types import SimpleNamespace

    from greenlight import server

    def req(xff):
        return SimpleNamespace(
            headers={"x-forwarded-for": xff}, client=SimpleNamespace(host="10.0.0.1")
        )

    assert server._client_ip(req("1.2.3.4")) == "1.2.3.4"
    # attacker prepends junk; the trusted appended hop still keys the limit
    assert server._client_ip(req("evil-spoof, 1.2.3.4")) == "1.2.3.4"
    assert server._client_ip(req("a, b, c, 1.2.3.4")) == "1.2.3.4"
    # no header at all -> the socket peer
    assert server._client_ip(SimpleNamespace(headers={}, client=SimpleNamespace(host="9.9.9.9")))


def test_owner_lookup_failure_denies_instead_of_allowing(monkeypatch):
    """A storage fault must never read as 'anonymous, anyone may act' on the
    delete path — that would route an OWNED run into the capability delete."""
    from greenlight import server, storage

    def boom(_run_id):
        raise storage.OwnerLookupError("gcs down")

    monkeypatch.setattr(server.storage, "load_owner", boom)
    monkeypatch.setattr(server, "_disk_record", lambda rid: None)
    res = client.delete("/api/runs/abc123def456")
    assert res.status_code == 503
    assert "verify" in res.json()["detail"].lower()


def test_pause_flag_and_invites_never_expire(monkeypatch):
    """The kill switch and invite redemptions share the research blob layer,
    which TTLs cached research at 7 days. A pause that lapses is not a switch."""
    import time as _t

    from greenlight import server, storage

    stale = {"paused": True, "by": "boss@example.com", "_cached_at": _t.time() - 30 * 24 * 3600}
    seen: dict = {}

    def fake_load(key, max_age_s=storage.RESEARCH_TTL_S):
        seen[key] = max_age_s
        # emulate the real TTL rule the blob layer applies
        if max_age_s is not None and _t.time() - stale["_cached_at"] > max_age_s:
            return None
        return stale

    monkeypatch.setattr(server.storage, "load_research", fake_load)
    assert _REAL_RUNS_PAUSED(), "a month-old pause must still be in force"
    assert seen[server._PAUSE_KEY] is None


def test_simulator_refused_on_case_studies(monkeypatch):
    """Each projection re-runs the evidence pipeline (model + embedding spend).
    Case studies are public marketing pages — their cut list is analysis, not a
    live control anyone can drive."""
    from greenlight import server

    monkeypatch.setattr(server, "_current_user", lambda req: {"sub": "u1", "email": "a@b.c"})
    body = {"run_id": "case_the_hangover", "cuts": [0], "extra": []}
    for path in ("/api/whatif", "/api/whatif/suggest"):
        res = client.post(path, json=body)
        assert res.status_code == 403, path
        assert "case studies" in res.json()["detail"].lower()


def test_stop_run_requires_owner(monkeypatch):
    """Owner-initiated stop: signed-out gets 401; a signed-in non-owner gets the
    same 404 as delete (no existence oracle); the owner of a running doc gets a
    clean terminal write ('stopped') even when no execution name was captured."""
    from greenlight import server

    monkeypatch.setattr(server, "_current_user", lambda req: None)
    assert client.post("/api/my/runs/abc123/stop").status_code == 401

    monkeypatch.setattr(server, "_current_user", lambda req: {"sub": "u1", "email": "a@b.c"})
    monkeypatch.setattr(server.storage, "load_owner", lambda rid: "someone-else")
    assert client.post("/api/my/runs/abc123/stop").status_code == 404

    monkeypatch.setattr(server.storage, "load_owner", lambda rid: "u1")
    monkeypatch.setattr(server.runstate, "get_state", lambda rid: {"status": "running"})
    written = {}
    monkeypatch.setattr(server.runstate, "run_set", lambda rid, st: written.update(st) or True)
    res = client.post("/api/my/runs/abc123/stop")
    assert res.status_code == 200 and res.json()["ok"]
    assert written["status"] == "stopped" and written["finished_at"]

    # already finished: no terminal overwrite
    monkeypatch.setattr(server.runstate, "get_state", lambda rid: {"status": "done"})
    res = client.post("/api/my/runs/abc123/stop")
    assert res.json().get("already_finished")


def test_static_js_is_text_not_binary():
    """A stray NUL byte in report.js made `file` and grep treat a shipped source
    file as binary — every grep over it silently returned nothing, which is how
    a code audit misses things. Keep the front end greppable."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "web" / "static"
    for js in sorted(root.glob("*.js")):
        raw = js.read_bytes()
        assert b"\x00" not in raw, f"{js.name} contains a NUL byte"
        raw.decode("utf-8")  # must be valid UTF-8
        control = {b for b in raw if b < 32 and b not in (9, 10, 13)}
        assert not control, f"{js.name} has control bytes {control}"


def test_abandoned_runs_do_not_latch_the_concurrency_cap(monkeypatch):
    """A worker killed mid-run never writes a terminal status. Counting those
    forever latched the cap closed: five zombies and every new run 429s until
    someone hand-edits Firestore."""
    import time as _t

    from greenlight import runstate

    fresh = {"status": "running", "started_at": _t.time() - 60}
    zombie = {"status": "running", "started_at": _t.time() - 5 * 3600}
    cutoff = _t.time() - runstate.RUN_MAX_AGE_S
    assert runstate._is_stale(zombie, cutoff)
    assert not runstate._is_stale(fresh, cutoff)
    # a doc with no started_at at all is never reaped (unknown age, not stale)
    assert not runstate._is_stale({"status": "running"}, cutoff)


def test_in_process_run_saves_the_record_before_declaring_done():
    """Reversed, a crash in the window left the ledger saying done/record_saved
    with nothing in storage — a paid run lost under a positive status."""
    import inspect

    from greenlight import server

    src = inspect.getsource(server._run_live)
    save_at = src.index("storage.save_record")
    status_at = src.index('"record_saved"')
    assert save_at < status_at, "save_record must precede the terminal run_set"


def test_replay_filed_briefs_match_the_run_view_counter():
    """run.js counts filings with /filed F\\d+/i. The live tool returns
    'Filed F203 (HIGH …)' and the replay synthesizer 'filed F203 · 2
    citation(s)' — a case-sensitive matcher counted 0 flags on every replay,
    which is the surface the demo is recorded from."""
    import re
    from pathlib import Path

    pattern = re.compile(r"filed F\d+", re.IGNORECASE)
    with client.stream("GET", "/api/replay?pace=0") as response:
        events = sse_events(response)
    briefs = [
        e.get("brief", "")
        for e in events
        if e.get("type") == "tool_result" and e.get("tool") == "file_flag"
    ]
    assert briefs, "replay emitted no file_flag results"
    assert all(pattern.search(b) for b in briefs), f"counter would miss: {briefs[:3]}"
    # and the front end must still be using the case-insensitive form
    run_js = (Path(__file__).resolve().parents[1] / "web" / "static" / "run.js").read_text()
    assert "/filed F\\d+/i" in run_js


def test_writer_page_has_no_undefined_poll_identifiers():
    """poll() referenced pollMisses / POLL_MAX_MISSES / progressFailed, none of
    which existed: under strict mode the first successful poll threw and the
    progress screen froze forever."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "web" / "static" / "writer.js").read_text()
    for ident, decl in (
        ("pollMisses", "let pollMisses"),
        ("POLL_MAX_MISSES", "const POLL_MAX_MISSES"),
        ("progressFailed", "function progressFailed"),
    ):
        assert ident in src and decl in src, f"{ident} is used but not declared"

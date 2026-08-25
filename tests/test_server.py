"""Replay endpoints of the web server. No live agent runs, no network.

Replay is the demo path (docs/DEMO.md: the video is recorded from replay, never
live), so these tests pin the SSE contract the front end renders from: meta first,
per-desk tool_call traces, verification verdicts, and a terminal `result` event
carrying the full record. pace=0 streams instantly through the same code path.
"""

import json

import pytest
from fastapi.testclient import TestClient

from greenlight.server import DESKS, app

client = TestClient(app)


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

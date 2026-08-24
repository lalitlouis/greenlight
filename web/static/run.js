/* Run page: one SSE code path for live and replay. Live and replayed streams speak
   the same event contract, so this page never knows which mode produced them.
   On completion, the record is stashed and the browser moves to the report page. */

"use strict";

const MAX_TRACE_LINES = 250;

const state = {
  es: null,
  runId: null,
  reportId: null, // where the report page finds the record
  mode: null,
  startedAt: null,
  timer: null,
  gotResult: false,
  phase: null,
  progress: 0,
  desks: {},
};

/* ---------- progress ---------- */

const PHASE_ORDER = ["triage", "desks", "verify", "adjudicate", "report"];

function setPhase(name) {
  const idx = PHASE_ORDER.indexOf(name);
  if (idx < 0 || idx < PHASE_ORDER.indexOf(state.phase)) return;
  state.phase = name;
  PHASE_ORDER.forEach((p, i) => {
    const node = $("phase-" + p);
    if (!node) return;
    node.classList.toggle("active", i === idx);
    node.classList.toggle("done", i < idx);
  });
}

function deskFraction(d) {
  return d.done ? 1 : Math.min(0.92, 1 - Math.exp(-d.calls / 9));
}

function bumpProgress() {
  let target = 2;
  const fracs = DESK_IDS.map((id) => deskFraction(state.desks[id] || { calls: 0 }));
  const anyDesk = DESK_IDS.some((id) => state.desks[id]?.started);
  if (state.phase === "triage") target = 5;
  if (state.phase === "desks" || anyDesk) {
    target = 8 + (fracs.reduce((a, b) => a + b, 0) / DESK_IDS.length) * 64;
  }
  if (state.phase === "verify") target = Math.max(78, state.progress + 1.2);
  if (state.phase === "adjudicate") target = Math.max(91, state.progress + 0.8);
  if (state.phase === "report") target = 100;
  const cap = { triage: 7, desks: 76, verify: 90, adjudicate: 97, report: 100 }[state.phase] ?? 5;
  state.progress = Math.max(state.progress, Math.min(target, cap));
  $("pbar-fill").style.width = state.progress.toFixed(1) + "%";
  $("pct").textContent = Math.round(state.progress) + "%";
}

/* ---------- desk panel ---------- */

function buildPanel() {
  const panel = $("panel");
  panel.textContent = "";
  $("pipe-log").textContent = "";
  state.desks = {};
  for (const [id, name, sub] of DESKS) {
    state.desks[id] = { calls: 0, flags: 0, done: false, started: false };
    const col = el("div", "card col");
    col.id = "col-" + id;
    const head = el("div", "col-head");
    head.appendChild(el("span", "nm", name));
    head.appendChild(el("span", "sub", sub));
    const st = el("span", "st queued");
    st.appendChild(el("span", "pulse"));
    st.appendChild(el("span", "st-txt", "QUEUED"));
    head.appendChild(st);
    col.appendChild(head);
    col.appendChild(el("div", "col-body"));
    panel.appendChild(col);
  }
}

function setDeskStatus(id) {
  const d = state.desks[id];
  const st = document.querySelector(`#col-${id} .st`);
  const txt = document.querySelector(`#col-${id} .st-txt`);
  if (!st || !txt) return;
  if (d.done) {
    st.className = "st done";
    txt.textContent = `DONE · ${d.calls} CALLS · ${d.flags} FLAGS`;
  } else if (d.started) {
    st.className = "st running";
    txt.textContent = `WORKING · ${d.calls} CALLS · ${d.flags} FLAGS`;
  }
}

function appendTrace(container, line) {
  container.appendChild(line);
  while (container.childElementCount > MAX_TRACE_LINES) {
    container.removeChild(container.firstChild);
  }
  container.scrollTop = container.scrollHeight;
}

function traceLine(ev) {
  if (ev.type === "tool_call") {
    if (ev.tool === "file_flag") {
      const sev = (ev.args && ev.args.severity) || "FYI";
      return el(
        "span",
        `tr t-flag sev-${sev}`,
        `flag filed · ${sev} · ${prettyCat(ev.args?.category)} · ${ev.args?.scene_ids || ""}`
      );
    }
    if (ev.tool === "note_open_question") {
      return el("span", "tr t-q", `open question — ${ev.args?.note || ""}`);
    }
    const args = Object.values(ev.args || {})
      .map((v) => String(v))
      .join(", ");
    const line = el("span", "tr t-call", `${ev.tool}(`);
    const em = el("em", null, args.length > 90 ? args.slice(0, 90) + "…" : args);
    line.appendChild(em);
    line.appendChild(document.createTextNode(")"));
    return line;
  }
  if (ev.type === "tool_result") {
    return el("span", "tr t-out", ev.brief || "");
  }
  const done = /^done\b/i.test(ev.text || "");
  return el("span", done ? "tr t-done" : "tr t-text", ev.text || "");
}

function handleDeskEvent(ev) {
  const d = state.desks[ev.agent];
  if (!d) return;
  d.started = true;
  if (ev.type === "tool_call") {
    d.calls += 1;
    if (ev.tool === "file_flag") d.flags += 1;
  }
  if (ev.type === "text" && /^done\b/i.test(ev.text || "")) d.done = true;
  setDeskStatus(ev.agent);
  appendTrace(document.querySelector(`#col-${ev.agent} .col-body`), traceLine(ev));
}

function handlePipeEvent(ev) {
  if (ev.agent === "verification_panel" || ev.agent === "adjudicator") {
    for (const id of DESK_IDS) {
      if (state.desks[id] && !state.desks[id].done && state.desks[id].started) {
        state.desks[id].done = true;
        setDeskStatus(id);
      }
    }
  }
  const line = el("span", "tr t-out");
  line.appendChild(el("span", "who", `[${ev.agent}] `));
  const body =
    ev.type === "text" ? ev.text : ev.brief || `${ev.tool}(${JSON.stringify(ev.args || {})})`;
  const rejected = /REJECTED/.test(body || "");
  line.appendChild(el("span", rejected ? "reject-line" : null, body || ""));
  appendTrace($("pipe-log"), line);
}

/* ---------- clock ---------- */

function startClock() {
  state.startedAt = Date.now();
  clearInterval(state.timer);
  state.timer = setInterval(() => {
    const s = Math.floor((Date.now() - state.startedAt) / 1000);
    $("elapsed").textContent =
      String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
  }, 500);
}

/* ---------- stream ---------- */

function handleEvent(ev) {
  switch (ev.type) {
    case "meta": {
      state.runId = ev.run_id;
      state.mode = ev.mode;
      state.reportId = ev.mode === "replay" ? ev.record_id || ev.run_id : ev.run_id;
      $("run-title").textContent = ev.script_title || "Analysis";
      const chip = $("mode-chip");
      chip.textContent = ev.mode === "replay" ? "REPLAY — RECORDED RUN" : "LIVE";
      chip.className = "chip " + (ev.mode === "replay" ? "replay" : "live");
      startClock();
      setPhase("triage");
      bumpProgress();
      break;
    }
    case "tool_call":
    case "tool_result":
    case "text":
      if (DESK_IDS.includes(ev.agent)) {
        setPhase("desks");
        handleDeskEvent(ev);
      } else {
        if (ev.agent === "verification_panel") setPhase("verify");
        else if (ev.agent === "adjudicator") setPhase("adjudicate");
        handlePipeEvent(ev);
      }
      bumpProgress();
      break;
    case "error":
      toast(
        ev.partial
          ? `pipeline error — partial results salvaged: ${ev.message}`
          : `run failed: ${ev.message}`,
        true
      );
      if (!ev.partial) {
        clearInterval(state.timer);
        state.es?.close();
      }
      break;
    case "result":
      onResult(ev.record);
      break;
  }
}

function onResult(record) {
  state.gotResult = true;
  setPhase("report");
  bumpProgress();
  clearInterval(state.timer);
  state.es?.close();
  for (const id of DESK_IDS) {
    if (state.desks[id]?.started) {
      state.desks[id].done = true;
      setDeskStatus(id);
    }
  }
  stashRecord(state.reportId, record);
  const target = `/report?run=${encodeURIComponent(state.reportId)}`;
  $("done-link").href = target;
  $("done-banner").classList.remove("hidden");
  setTimeout(() => {
    window.location.href = target;
  }, 1400);
}

function startStream(url) {
  buildPanel();
  const es = new EventSource(url);
  state.es = es;
  let receivedAny = false;
  es.onopen = () => {
    if (receivedAny) buildPanel(); // server resends history on reconnect
  };
  es.onerror = () => {
    if (!state.gotResult) toast("stream interrupted — reconnecting…", true);
  };
  es.onmessage = (msg) => {
    receivedAny = true;
    let ev;
    try {
      ev = JSON.parse(msg.data);
    } catch {
      return;
    }
    handleEvent(ev);
  };
}

document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  if (params.get("replay") != null) {
    const record = params.get("record");
    startStream("/api/replay" + (record ? `?record=${encodeURIComponent(record)}` : ""));
  } else if (params.get("id")) {
    startStream(`/api/runs/${encodeURIComponent(params.get("id"))}/events`);
  } else {
    toast("No analysis specified — starting the recorded demo.", false);
    startStream("/api/replay");
  }
});

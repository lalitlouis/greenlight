/* Run page: one SSE code path for live and replay. Live and replayed streams speak
   the same event contract, so this page never knows which mode produced them.
   On completion, the record is stashed and the browser moves to the report page. */

"use strict";

const MAX_TRACE_LINES = 250;
let SCENE_HEADINGS = {}; // scene_id -> heading, for narrating which scene is being read
const rt = {
  built: false,
  backlog: [], // ops that arrived before the strip existed
  lastScene: {}, // desk -> scene_id
  pendingPin: {}, // desk -> pin element awaiting its flag id
  pins: {}, // flag_id -> pin element
  autoFollow: true,
};

async function loadSceneHeadings(id) {
  try {
    const res = await fetch(`/api/script/${encodeURIComponent(id)}`);
    if (!res.ok) return;
    const data = await res.json();
    for (const s of data.scenes || []) SCENE_HEADINGS[s.scene_id] = s.heading;
    buildSceneStrip(data.scenes || []);
  } catch {
    /* narration degrades to bare scene ids */
  }
}

function buildSceneStrip(scenes) {
  const strip = $("scene-strip");
  if (!strip || !scenes.length) return;
  strip.textContent = "";
  for (const s of scenes) {
    const card = el("div", "rt-scene");
    card.id = "rts-" + s.scene_id;
    const head = el("div", "rts-head");
    head.appendChild(el("span", "rts-num", s.scene_id));
    head.appendChild(el("span", "rts-heading", s.heading.slice(0, 60)));
    head.appendChild(el("span", "rts-page", "p." + s.page));
    card.appendChild(head);
    card.appendChild(el("div", "rts-dots"));
    card.appendChild(el("div", "rts-pins"));
    strip.appendChild(card);
  }
  rt.built = true;
  const ops = rt.backlog.splice(0);
  for (const op of ops) op();
  strip.addEventListener("wheel", pauseFollow, { passive: true });
  strip.addEventListener("touchstart", pauseFollow, { passive: true });
}

function pauseFollow() {
  if (!rt.autoFollow) return;
  rt.autoFollow = false;
  $("follow-chip")?.classList.remove("hidden");
}

function followTo(node) {
  if (!rt.autoFollow || !node) return;
  node.scrollIntoView({ behavior: "smooth", block: "center" });
}

function rtOp(fn) {
  if (rt.built) fn();
  else rt.backlog.push(fn);
}

function moveDeskDot(agent, sceneId) {
  rtOp(() => {
    document.querySelectorAll(`.rt-dot.dot-${agent}`).forEach((d) => d.remove());
    const card = $("rts-" + sceneId);
    if (!card) return;
    const dot = el("span", `rt-dot dot-${agent}`);
    dot.title = (DESKS.find((d) => d[0] === agent) || [])[1] || agent;
    card.querySelector(".rts-dots").appendChild(dot);
    card.classList.add("rts-active", "glow-" + agent);
    setTimeout(() => card.classList.remove("glow-" + agent), 1800);
    rt.lastScene[agent] = sceneId;
    followTo(card);
  });
}

function rippleScene(agent, title) {
  rtOp(() => {
    const card = $("rts-" + (rt.lastScene[agent] || ""));
    if (!card) return;
    const rip = el("span", "rt-ripple", "🔎");
    rip.title = title || "researching";
    card.querySelector(".rts-dots").appendChild(rip);
    setTimeout(() => rip.remove(), 2600);
  });
}

function dropPin(agent, severity, category, sceneIds) {
  rtOp(() => {
    const ids = (String(sceneIds || "").match(/S\d+/g) || []);
    const card = $("rts-" + ids[0]);
    if (!card) return;
    const pin = el("span", `rt-pin sev-${severity}`);
    pin.appendChild(el("b", null, severity));
    pin.appendChild(el("span", null, prettyCat(category) + (ids.length > 1 ? ` +${ids.length - 1}` : "")));
    card.querySelector(".rts-pins").appendChild(pin);
    rt.pendingPin[agent] = pin;
    if (window.FX?.on) {
      gsap.fromTo(pin, { scale: 0, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.45, ease: "back.out(1.8)" });
    }
    followTo(card);
  });
}

function assignPinId(agent, brief) {
  const m = (brief || "").match(/F\d+/);
  rtOp(() => {
    const pin = rt.pendingPin[agent];
    if (!pin) return;
    delete rt.pendingPin[agent];
    if (m) rt.pins[m[0]] = pin;
    else pin.remove(); // the filing was rejected by validation — never landed
  });
}

function pinVerdict(fid, verdict) {
  rtOp(() => {
    const pin = rt.pins[fid];
    if (!pin) return;
    if (verdict === "SUPPORTED") {
      pin.classList.add("pin-ok");
    } else if (verdict === "PARTIAL") {
      pin.classList.add("pin-partial");
    } else {
      pin.classList.add("pin-rejected");
      if (window.FX?.on) gsap.to(pin, { opacity: 0.45, duration: 0.6 });
    }
  });
}

function sceneLabel(sid) {
  const h = SCENE_HEADINGS[sid];
  return h ? `${sid} · ${h.slice(0, 44)}` : sid;
}

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

function buildDeskRail() {
  const rail = $("desk-rail");
  if (!rail) return;
  rail.textContent = "";
  for (const [id, name] of DESKS) {
    const row = el("div", "rail-row rail-" + id);
    row.id = "rail-" + id;
    const top = el("div", "rail-top");
    top.appendChild(el("span", "rail-dot"));
    top.appendChild(el("b", null, name));
    top.appendChild(el("span", "rail-status", "Waiting"));
    row.appendChild(top);
    row.appendChild(el("p", "rail-spot", "…"));
    rail.appendChild(row);
  }
}

function buildPanel() {
  buildDeskRail();
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
    st.appendChild(el("span", "st-txt", "Waiting"));
    head.appendChild(st);
    head.appendChild(el("p", "spotlight", "Waiting for the worklist…"));
    col.appendChild(head);
    col.appendChild(el("div", "col-body"));
    panel.appendChild(col);
  }
  window.FX?.staggerIn(panel.querySelectorAll(".col"));
}

function setDeskStatus(id) {
  const d = state.desks[id];
  const st = document.querySelector(`#col-${id} .st`);
  const txt = document.querySelector(`#col-${id} .st-txt`);
  if (st && txt) {
    if (d.done) {
      st.className = "st done";
      txt.textContent = `Done · ${d.calls} calls · ${d.flags} flags`;
    } else if (d.started) {
      st.className = "st running";
      txt.textContent = `Working · ${d.calls} calls · ${d.flags} flags`;
    }
  }
  const rail = document.querySelector(`#rail-${id} .rail-status`);
  const row = $("rail-" + id);
  if (rail) {
    rail.textContent = d.done ? `Done · ${d.flags} flags` : d.started ? `${d.calls} calls` : "Waiting";
    row?.classList.toggle("rail-working", d.started && !d.done);
    row?.classList.toggle("rail-done", d.done);
  }
}

function appendTrace(container, line) {
  container.appendChild(line);
  while (container.childElementCount > MAX_TRACE_LINES) {
    container.removeChild(container.firstChild);
  }
  container.scrollTop = container.scrollHeight;
}

function trim(s, n) {
  s = String(s || "").replace(/^\[?['"]?|['"]?\]?$/g, "");
  return s.length > n ? s.slice(0, n) + "…" : s;
}

/* Every event becomes a sentence a filmmaker can read — no function-call syntax. */
function traceLine(ev) {
  if (ev.type === "tool_call") {
    const a = ev.args || {};
    switch (ev.tool) {
      case "read_scene":
        return el("span", "tr t-call", `Reading ${sceneLabel(a.scene_id)}`);
      case "find_in_script":
        return el("span", "tr t-call", `Searching the script for “${trim(a.pattern, 40)}”`);
      case "research":
        return el("span", "tr t-call", `Researching: ${trim(a.objective, 90)}`);
      case "query_precedent":
        return el("span", "tr t-call", `Matching against released films: ${trim(a.text, 70)}`);
      case "file_rating_prediction":
        return el("span", "tr t-flag", `Filing the rating prediction: ${a.predicted || ""}`);
      case "file_flag": {
        const sev = a.severity || "FYI";
        return el(
          "span",
          `tr t-flag sev-${sev}`,
          `Filing a ${sev} finding — ${prettyCat(a.category)} (${trim(a.scene_ids, 30)})`
        );
      }
      case "note_open_question":
        return el("span", "tr t-q", `Noting an open question — ${trim(a.question || a.note, 80)}`);
      case "done":
        return el("span", "tr t-done", `Closing the desk: ${trim(a.reason, 90)}`);
      default:
        return el("span", "tr t-call", `${prettyCat(ev.tool)}…`);
    }
  }
  if (ev.type === "tool_result") {
    return el("span", "tr t-out", ev.brief || "");
  }
  const done = /^done\b/i.test(ev.text || "");
  return el("span", done ? "tr t-done" : "tr t-text", ev.text || "");
}

function setDeskSpotlight(agent, text) {
  const node = document.querySelector(`#col-${agent} .spotlight`);
  if (node) node.textContent = text;
  const railNode = document.querySelector(`#rail-${agent} .rail-spot`);
  if (railNode) railNode.textContent = text;
}

function handleDeskEvent(ev) {
  const d = state.desks[ev.agent];
  if (!d) return;
  d.started = true;
  if (ev.type === "tool_call") {
    d.calls += 1;
    if (ev.tool === "file_flag") d.flags += 1;
    const a = ev.args || {};
    if (ev.tool === "read_scene") moveDeskDot(ev.agent, a.scene_id);
    else if (ev.tool === "research") rippleScene(ev.agent, trim(a.objective, 80));
    else if (ev.tool === "file_flag") dropPin(ev.agent, a.severity || "FYI", a.category, a.scene_ids);
    if (ev.tool === "read_scene") setDeskSpotlight(ev.agent, `Now reading ${sceneLabel(a.scene_id)}`);
    else if (ev.tool === "research") setDeskSpotlight(ev.agent, `Researching: ${trim(a.objective, 60)}`);
    else if (ev.tool === "query_precedent") setDeskSpotlight(ev.agent, "Consulting released-film comparables…");
    else if (ev.tool === "file_flag") setDeskSpotlight(ev.agent, `Filed ${a.severity || ""} — ${prettyCat(a.category)}`);
  }
  if (ev.type === "tool_result" && ev.tool === "file_flag") assignPinId(ev.agent, ev.brief);
  if (ev.type === "text" && /^done\b/i.test(ev.text || "")) {
    d.done = true;
    setDeskSpotlight(ev.agent, "Desk closed.");
    document.querySelectorAll(`.rt-dot.dot-${ev.agent}`).forEach((n) => n.remove());
  }
  if (ev.type === "text" && /^done\b/i.test(ev.text || "")) d.done = true;
  setDeskStatus(ev.agent);
  appendTrace(document.querySelector(`#col-${ev.agent} .col-body`), traceLine(ev));
}

const VERDICT_TONE_RUN = { SUPPORTED: "ok", PARTIAL: "mid", REJECTED: "bad", UNSUPPORTED: "bad" };

function studioCard(fid, category, severity, verdict, reason) {
  const feed = $("studio-feed");
  if (!feed) return;
  const card = el("div", "studio-card sc-" + (VERDICT_TONE_RUN[verdict] || "mid"));
  const top = el("div", "sc-top");
  top.appendChild(el("span", `sev-chip sev-${severity}`, severity));
  if (category) top.appendChild(el("b", null, prettyCat(category)));
  top.appendChild(el("span", "sc-fid", fid));
  top.appendChild(el("span", "sc-verdict", verdict === "UNSUPPORTED" ? "REJECTED" : verdict));
  card.appendChild(top);
  if (reason) card.appendChild(el("p", "sc-reason", reason));
  feed.appendChild(card);
  feed.scrollTop = feed.scrollHeight;
}

function maybeStudioEvent(ev) {
  /* Live verdicts arrive as "⚖ F203|category|SEV|VERDICT|reason"; replay's come
     as verify_flag tool_results "F203 · VERDICT — reason". Both become cards. */
  if (ev.agent !== "verification_panel") return false;
  if (ev.type === "text" && (ev.text || "").startsWith("⚖ ")) {
    const [fid, cat, sev, verdict, reason] = ev.text.slice(2).split("|");
    studioCard(fid, cat, sev, verdict, reason);
    pinVerdict(fid, verdict);
    return true;
  }
  if (ev.type === "tool_result" && ev.tool === "verify_flag") {
    const m = (ev.brief || "").match(/^(F\d+)\s*·\s*(\w+)\s*(?:—\s*(.*))?$/);
    if (m) {
      studioCard(m[1], "", "FYI", m[2], m[3] || "");
      pinVerdict(m[1], m[2]);
      return true;
    }
  }
  return false;
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

/* ---------- status narration: the quiet stretches are when models think ---------- */

const QUIET_LINES = {
  none: ["Connecting to the analysis…", "Waking the pipeline — a cold start can take a few seconds…"],
  triage: [
    "Triage is reading your screenplay scene by scene…",
    "Extracting every brand, song, person, stunt, and sensitive beat…",
    "Building each desk's worklist…",
  ],
  desks: [
    "The desks are researching — live web lookups take a moment…",
    "Long pauses are normal: a desk is reading sources before it files anything…",
    "Findings without citations get rejected, so the desks read carefully…",
  ],
  verify: ["The verifier is re-reading every citation…", "Unsupported claims are being rejected…"],
  adjudicate: ["The adjudicator is merging duplicates and resolving conflicts…"],
  report: ["Assembling your report…"],
};

let lastEventAt = Date.now();
let quietIdx = 0;

function tickStatus() {
  const node = $("run-status");
  if (!node || state.gotResult) return;
  const quietFor = (Date.now() - lastEventAt) / 1000;
  const lines = QUIET_LINES[state.phase || "none"] || QUIET_LINES.none;
  if (quietFor > 4) {
    node.textContent = lines[quietIdx % lines.length];
    quietIdx += 1;
  }
}
setInterval(tickStatus, 5000);

function noteActivity(ev) {
  lastEventAt = Date.now();
  const node = $("run-status");
  if (!node) return;
  if (ev.type === "tool_call" && DESK_IDS.includes(ev.agent)) {
    const desk = DESKS.find((d) => d[0] === ev.agent);
    const verb =
      ev.tool === "research"
        ? "is researching"
        : ev.tool === "file_flag"
          ? "just filed a finding"
          : ev.tool === "query_precedent"
            ? "is pulling comparables"
            : "is reading the script";
    node.textContent = `${desk ? desk[1] : ev.agent} ${verb}…`;
  } else if (ev.agent === "verification_panel") {
    node.textContent = "Verifying citations…";
  } else if (ev.agent === "adjudicator") {
    node.textContent = "Adjudicating findings…";
  }
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
      loadSceneHeadings(state.reportId);
      $("run-title").textContent = ev.script_title || "Analysis";
      const chip = $("mode-chip");
      chip.textContent = ev.mode === "replay" ? "Replay · recorded run" : "Live";
      chip.className = "chip " + (ev.mode === "replay" ? "replay" : "live");
      startClock();
      setPhase("triage");
      bumpProgress();
      break;
    }
    case "tool_call":
    case "tool_result":
    case "text":
      noteActivity(ev);
      if (DESK_IDS.includes(ev.agent)) {
        setPhase("desks");
        handleDeskEvent(ev);
      } else {
        if (ev.agent === "verification_panel") setPhase("verify");
        else if (ev.agent === "adjudicator") setPhase("adjudicate");
        if (!maybeStudioEvent(ev)) handlePipeEvent(ev);
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
  beacon("info", "stream_result", state.mode || "");
  const statusNode = $("run-status");
  if (statusNode) statusNode.textContent = "Done — opening your report.";
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
  if (typeof window.confetti === "function") {
    window.confetti({
      particleCount: 110,
      spread: 75,
      origin: { y: 0.7 },
      colors: ["#22c55e", "#34d399", "#a5b4fc", "#fcd34d", "#7dd3fc"],
      disableForReducedMotion: true,
    });
  }
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
  beacon("info", "stream_open", url);
  setTimeout(() => {
    if (!receivedAny) beacon("error", "stream_no_events_10s", url);
  }, 10000);
  es.onopen = () => {
    if (receivedAny) buildPanel(); // server resends history on reconnect
  };
  let streamErrors = 0;
  es.onerror = () => {
    if (state.gotResult) return;
    streamErrors += 1;
    beacon("error", "stream_error", url + " readyState=" + es.readyState + " n=" + streamErrors);
    if (streamErrors >= 4 && !receivedAny) {
      // The stream never opened — retrying forever is a lie. Say so and offer outs.
      es.close();
      clearInterval(state.timer);
      const node = $("run-status");
      if (node) {
        node.textContent =
          "This analysis could not be streamed — it may have been deleted or the link is stale.";
      }
      const banner = $("done-banner");
      if (banner) {
        banner.classList.remove("hidden");
        banner.querySelector("b").textContent = "Couldn't load this analysis.";
        const link = $("done-link");
        link.textContent = "Watch the recorded demo instead";
        link.href = "/run?replay=1";
      }
      return;
    }
    toast("stream interrupted — reconnecting…", true);
  };
  let firstEvent = true;
  es.onmessage = (msg) => {
    if (firstEvent) {
      firstEvent = false;
      beacon("info", "stream_first_event", url);
    }
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
  $("detail-toggle")?.addEventListener("click", () => {
    const on = document.body.classList.toggle("show-detail");
    $("detail-toggle").textContent = on ? "Hide detail" : "Detail view";
  });
  $("follow-chip")?.addEventListener("click", () => {
    rt.autoFollow = true;
    $("follow-chip").classList.add("hidden");
  });
  $("studio-toggle")?.addEventListener("click", () => {
    const body = $("studio-body");
    const hidden = body.classList.toggle("hidden");
    $("studio-toggle").textContent = hidden ? "Show" : "Hide";
  });
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

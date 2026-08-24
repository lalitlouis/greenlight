/* GREENLIGHT front end. One SSE code path for live and replay: both streams speak
   the same event contract ({type: meta|tool_call|tool_result|text|error|result}),
   so the panel, report, and script views never know which mode produced them.
   Vanilla JS, no build step, no network beyond this origin. */

"use strict";

const DESKS = [
  ["clearance_counsel", "Clearance Counsel", "DESK 01"],
  ["ratings_board", "Ratings Board", "DESK 02"],
  ["safety_underwriter", "Safety Underwriter", "DESK 03"],
  ["territory_censor", "Territory Censor", "DESK 04"],
];
const DESK_IDS = DESKS.map((d) => d[0]);
const SEVS = ["BLOCKER", "HIGH", "MEDIUM", "LOW", "FYI"];
const MAX_TRACE_LINES = 250;

const state = {
  es: null,
  runId: null,
  mode: null,
  record: null,
  scenes: null,
  source: null,
  startedAt: null,
  timer: null,
  gotResult: false,
  phase: null,
  progress: 0,
  desks: {}, // id -> {calls, flags, done, started}
};

const $ = (id) => document.getElementById(id);

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function toast(msg, isError) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "toast" + (isError ? " error" : "");
  clearTimeout(t._hide);
  t._hide = setTimeout(() => t.classList.add("hidden"), 6000);
}

function money(range) {
  if (!range || range.length < 2) return null;
  const f = (n) => "$" + Math.round(n).toLocaleString("en-US");
  return `${f(range[0])}–${f(range[1])}`;
}

/* ---------------- progress ----------------
   Phase is inferred from event authors; percent is a monotonic estimate:
   desks dominate the timeline, each desk's share eased on its call count. */

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
  // Eases toward 1 with activity; a desk is only certainly finished when done.
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

function resetProgress() {
  state.phase = null;
  state.progress = 0;
  PHASE_ORDER.forEach((p) => $("phase-" + p)?.classList.remove("active", "done"));
  $("pbar-fill").style.width = "0%";
  $("pct").textContent = "0%";
}

/* ---------------- views ---------------- */

function showView(name) {
  for (const v of ["intake", "panel", "report", "script"]) {
    $("view-" + v).classList.toggle("hidden", v !== name);
  }
  document.querySelectorAll(".tab").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === name);
  });
}

document.querySelectorAll(".tab").forEach((b) => {
  b.addEventListener("click", () => showView(b.dataset.view));
});

/* ---------------- panel ---------------- */

function buildPanel() {
  const panel = $("panel");
  panel.textContent = "";
  $("pipe-log").textContent = "";
  state.desks = {};
  resetProgress();
  for (const [id, name, tag] of DESKS) {
    state.desks[id] = { calls: 0, flags: 0, done: false, started: false };
    const col = el("div", "col");
    col.id = "col-" + id;
    const head = el("div", "col-head");
    const nm = el("span", "nm", name);
    nm.appendChild(el("span", "label", "  " + tag));
    const st = el("span", "st queued");
    st.appendChild(el("span", "pulse"));
    st.appendChild(el("span", "st-txt", "QUEUED"));
    head.appendChild(nm);
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
    txt.textContent = `RUNNING · ${d.calls} CALLS · ${d.flags} FLAGS`;
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
        `file_flag · ${sev} · ${ev.args?.category || ""} · ${ev.args?.scene_ids || ""}`
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
  // Anything from verification onward means every desk has finished.
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
  const body = ev.type === "text" ? ev.text : ev.brief || `${ev.tool}(${JSON.stringify(ev.args || {})})`;
  const rejected = /REJECTED/.test(body || "");
  line.appendChild(el("span", rejected ? "reject-line" : null, body || ""));
  appendTrace($("pipe-log"), line);
}

/* ---------------- stream ---------------- */

function startStream(url) {
  if (state.es) state.es.close();
  state.gotResult = false;
  state.record = null;
  state.scenes = null;
  buildPanel();
  showView("panel");
  $("tabs").classList.remove("hidden");
  $("tab-report").disabled = true;
  $("tab-script").disabled = true;

  const es = new EventSource(url);
  state.es = es;
  let receivedAny = false;

  es.onopen = () => {
    // On auto-reconnect the server resends history; rebuild so nothing duplicates.
    if (receivedAny) buildPanel();
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

function handleEvent(ev) {
  switch (ev.type) {
    case "meta": {
      state.runId = ev.run_id;
      state.mode = ev.mode;
      $("run-title").textContent = ev.script_title || "";
      const chip = $("mode-chip");
      chip.textContent = ev.mode === "replay" ? "REPLAY — CACHED RUN" : "LIVE";
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
        stopClock();
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
  state.record = record;
  setPhase("report");
  bumpProgress();
  stopClock();
  state.es?.close();
  for (const id of DESK_IDS) {
    if (state.desks[id]?.started) {
      state.desks[id].done = true;
      setDeskStatus(id);
    }
  }
  renderReport(record);
  $("tab-report").disabled = false;
  fetchScript();
  setTimeout(() => showView("report"), 900);
}

async function fetchScript() {
  try {
    const res = await fetch(`/api/script/${state.runId}`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    state.source = data.source;
    state.scenes = data.scenes;
    renderScript();
    $("tab-script").disabled = false;
  } catch (e) {
    toast("script view unavailable: " + e.message, true);
  }
}

/* ---------------- clock ---------------- */

function startClock() {
  state.startedAt = Date.now();
  clearInterval(state.timer);
  state.timer = setInterval(() => {
    const s = Math.floor((Date.now() - state.startedAt) / 1000);
    $("elapsed").textContent =
      String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
  }, 500);
}
function stopClock() {
  clearInterval(state.timer);
}

/* ---------------- report ---------------- */

function citationCard(c, idx, total) {
  const wrap = el("div");
  wrap.appendChild(el("div", "blk-label", `CITATION — ${idx + 1} OF ${total}`));
  const card = el("div", "cite");
  card.appendChild(el("q", null, c.excerpt || ""));
  const src = el("div", "src");
  src.appendChild(el("span", "via", (c.via || c.source_type || "source").replace("_", " ").toUpperCase()));
  if (c.url) {
    const a = el("a", null, c.url.replace(/^https?:\/\//, "").slice(0, 60));
    a.href = c.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    src.appendChild(a);
  }
  if (c.title) src.appendChild(el("span", null, "· " + c.title));
  card.appendChild(src);
  wrap.appendChild(card);
  return wrap;
}

function flagExpand(f) {
  const ex = el("div", "expand");
  const cites = f.citations || [];
  const citeWrap = el("div");
  cites.forEach((c, i) => citeWrap.appendChild(citationCard(c, i, cites.length)));
  ex.appendChild(citeWrap);

  const r = f.remedy || {};
  const rem = el("div", "remedy");
  rem.appendChild(el("span", "act", r.action || "REVIEW"));
  const parts = [r.detail || ""];
  const cost = money(r.est_cost_usd);
  if (cost) parts.push(`Est. ${cost}.`);
  if (r.est_added_days) parts.push(`~${r.est_added_days} added day(s).`);
  rem.appendChild(el("p", null, parts.join(" ")));
  ex.appendChild(rem);

  if (f.confidence != null) {
    ex.appendChild(el("span", "conf", `desk confidence ${Math.round(f.confidence * 100)}%`));
  }
  if (f.rejection_reason) {
    const rej = el("div", "rejection");
    rej.appendChild(el("b", null, "REJECTED IN VERIFICATION — "));
    rej.appendChild(document.createTextNode(f.rejection_reason));
    ex.appendChild(rej);
  }
  return ex;
}

function flagRow(f, opts) {
  const { rejected = false, expanded = false } = opts || {};
  const row = el("article", "flag" + (rejected ? " rejected" : ""));
  row.id = "flag-" + f.flag_id;
  row.appendChild(el("span", "sev-bar bar-" + f.severity));

  const scenes = el("div", "scenes");
  scenes.appendChild(el("span", null, f.flag_id));
  for (const sid of f.scene_ids || []) {
    const b = el("button", "scene-link", sid);
    b.type = "button";
    b.title = "Show in script";
    b.addEventListener("click", () => gotoScene(sid));
    scenes.appendChild(b);
  }
  row.appendChild(scenes);

  const main = el("div", "flag-main");
  const top = el("div", "flag-top");
  top.appendChild(el("span", `sev-chip sev-${f.severity}`, f.severity));
  top.appendChild(el("span", "cat", (f.category || "").replace(/_/g, " ")));
  top.appendChild(el("span", "by", f.agent || ""));
  main.appendChild(top);
  main.appendChild(el("p", "finding", f.finding || ""));

  const cites = f.citations || [];
  const hosts = [...new Set(cites.map((c) => (c.url || "").split("/")[2]).filter(Boolean))];
  const toggle = el(
    "button",
    "cite-toggle",
    `${cites.length} citation${cites.length === 1 ? "" : "s"} · ${hosts.join(", ")} ▾`
  );
  toggle.type = "button";
  const ex = flagExpand(f);
  if (!expanded) ex.classList.add("hidden");
  toggle.addEventListener("click", () => ex.classList.toggle("hidden"));
  main.appendChild(toggle);
  main.appendChild(ex);
  row.appendChild(main);

  const costBox = el("div", "cost");
  const cost = money(f.remedy?.est_cost_usd);
  if (cost) {
    costBox.appendChild(el("b", null, cost));
    costBox.appendChild(document.createTextNode("estimate"));
  } else {
    costBox.appendChild(el("b", null, f.remedy?.action || ""));
  }
  row.appendChild(costBox);
  return row;
}

function renderReport(record) {
  const root = $("report");
  root.textContent = "";
  const rep = record.report || {};
  const counts = rep.counts || {};
  const score = rep.greenlight_score ?? "—";
  const blockers = counts.BLOCKER || 0;
  const tone = blockers > 0 || score < 40 ? "bad" : score < 75 ? "mid" : "good";

  const head = el("div", "rpt-head");
  const scoreBox = el("div", "score " + tone);
  if (typeof score === "number") scoreBox.style.setProperty("--scorepct", String(score));
  scoreBox.appendChild(el("b", null, String(score)));
  scoreBox.appendChild(el("span", "of", "/100"));
  head.appendChild(scoreBox);

  const meta = el("div", "score-meta");
  const verdict =
    blockers > 0
      ? `NOT CLEARED — ${blockers} BLOCKER${blockers === 1 ? "" : "S"}`
      : tone === "good"
        ? "CLEARED — CONDITIONS BELOW"
        : "CONDITIONAL — REMEDIES REQUIRED";
  meta.appendChild(el("span", "verdict " + tone, verdict));
  const proj = el("span", "proj");
  proj.appendChild(
    document.createTextNode(
      `${(record.flags || []).length} findings · ` +
        `${(record.rejected_flags || []).length} rejected in verification · ` +
        `${(record.entities || []).length} entities`
    )
  );
  meta.appendChild(proj);
  const cost = money(rep.est_clearance_cost_usd);
  if (cost) {
    const c = el("span", "proj");
    c.appendChild(document.createTextNode("est. clearance cost "));
    c.appendChild(el("b", null, cost));
    meta.appendChild(c);
  }
  meta.appendChild(el("span", "est-note", "COST FIGURES ARE ESTIMATES, NOT QUOTES"));
  head.appendChild(meta);

  const tally = el("div", "tally");
  for (const sev of SEVS) {
    const cell = el("div", "sev-" + sev);
    cell.appendChild(el("b", "sev-" + sev, String(counts[sev] || 0)));
    cell.appendChild(el("span", null, sev));
    tally.appendChild(cell);
  }
  head.appendChild(tally);
  root.appendChild(head);

  // The invariant, enforced at render: a flag without a citation does not exist.
  const cited = (record.flags || []).filter((f) => (f.citations || []).length > 0);
  const secFlags = el("div", "section-head");
  secFlags.appendChild(el("span", "label", `Findings — ${cited.length}, every one cited`));
  root.appendChild(secFlags);
  const flags = el("div", "flags");
  cited.forEach((f) => flags.appendChild(flagRow(f, { expanded: f.severity === "BLOCKER" })));
  root.appendChild(flags);

  const rejectedFlags = record.rejected_flags || [];
  if (rejectedFlags.length) {
    const sec = el("div", "section-head");
    sec.appendChild(
      el("span", "label", `Rejected in verification — ${rejectedFlags.length} · an independent verifier read every citation`)
    );
    root.appendChild(sec);
    const list = el("div", "flags");
    rejectedFlags.forEach((f) => list.appendChild(flagRow(f, { rejected: true, expanded: true })));
    root.appendChild(list);
  }

  const oq = record.open_questions || {};
  const oqItems = Object.entries(oq).flatMap(([desk, qs]) => qs.map((q) => [desk, q]));
  if (oqItems.length) {
    const sec = el("div", "section-head");
    sec.appendChild(el("span", "label", `Open questions — ${oqItems.length} honest unknowns`));
    root.appendChild(sec);
    const ul = el("ul", "plain-list");
    for (const [desk, q] of oqItems) {
      const li = el("li");
      li.appendChild(el("span", "who", desk));
      li.appendChild(document.createTextNode(q));
      ul.appendChild(li);
    }
    root.appendChild(ul);
  }

  const notes = record.adjudication_notes || [];
  if (notes.length) {
    const sec = el("div", "section-head");
    sec.appendChild(el("span", "label", `Adjudication — merges and conflict resolutions`));
    root.appendChild(sec);
    const ul = el("ul", "plain-list");
    for (const n of notes) ul.appendChild(el("li", null, n));
    root.appendChild(ul);
  }
}

/* ---------------- marked-up script ---------------- */

function flagsByScene() {
  const map = {};
  const all = (state.record?.flags || []).filter((f) => (f.citations || []).length > 0);
  for (const f of all) {
    for (const sid of f.scene_ids || []) (map[sid] = map[sid] || []).push(f);
  }
  return map;
}

function worstSeverity(flags) {
  for (const sev of SEVS) if (flags.some((f) => f.severity === sev)) return sev;
  return null;
}

function renderScript() {
  const root = $("script");
  root.textContent = "";
  if (!state.scenes || state.source == null) return;
  const byScene = flagsByScene();
  const view = el("div", "scriptview");

  for (const scene of state.scenes) {
    const flags = byScene[scene.scene_id] || [];
    const worst = worstSeverity(flags);
    const row = el("div", "scene-row" + (worst ? " flagged-" + worst : ""));
    row.id = "scene-" + scene.scene_id;

    const text = el("pre", "scene-text");
    text.appendChild(el("span", "sid", `${scene.scene_id} · p.${scene.page}`));
    // raw_span slices the ORIGINAL source: report and script are one object.
    text.appendChild(
      document.createTextNode(state.source.slice(scene.raw_span[0], scene.raw_span[1]).trimEnd())
    );
    row.appendChild(text);

    const gutter = el("div", "gutter");
    for (const f of flags) {
      const note = el("div", "gnote gn-" + f.severity);
      note.appendChild(
        el("span", "gt", `${f.severity} · ${f.flag_id} · ${(f.category || "").replace(/_/g, " ")}`)
      );
      note.appendChild(el("p", null, (f.finding || "").slice(0, 180) + ((f.finding || "").length > 180 ? "…" : "")));
      note.title = "Open in report";
      note.addEventListener("click", () => gotoFlag(f.flag_id));
      gutter.appendChild(note);
    }
    row.appendChild(gutter);
    view.appendChild(row);
  }
  root.appendChild(view);
}

function flash(node) {
  node.classList.add("hilite");
  setTimeout(() => node.classList.remove("hilite"), 2200);
}

function gotoScene(sceneId) {
  if ($("tab-script").disabled) return;
  showView("script");
  const node = $("scene-" + sceneId);
  if (node) {
    node.scrollIntoView({ behavior: "smooth", block: "start" });
    flash(node);
  }
}

function gotoFlag(flagId) {
  showView("report");
  const node = $("flag-" + flagId);
  if (node) {
    node.querySelector(".expand")?.classList.remove("hidden");
    node.scrollIntoView({ behavior: "smooth", block: "center" });
    flash(node);
  }
}

/* ---------------- intake ---------------- */

async function upload(file) {
  const form = new FormData();
  form.append("screenplay", file, file.name);
  try {
    const res = await fetch("/api/runs", { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    const { run_id } = await res.json();
    startStream(`/api/runs/${run_id}/events`);
  } catch (e) {
    toast("upload failed: " + e.message, true);
  }
}

$("pick-btn").addEventListener("click", () => $("file-input").click());
$("file-input").addEventListener("change", (e) => {
  if (e.target.files[0]) upload(e.target.files[0]);
});
$("replay-btn").addEventListener("click", () => startStream("/api/replay"));

const dz = $("dropzone");
for (const evName of ["dragenter", "dragover"]) {
  dz.addEventListener(evName, (e) => {
    e.preventDefault();
    dz.classList.add("dragging");
  });
}
dz.addEventListener("dragleave", () => dz.classList.remove("dragging"));
dz.addEventListener("drop", (e) => {
  e.preventDefault();
  dz.classList.remove("dragging");
  if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]);
});

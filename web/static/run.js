/* Run page: one SSE code path for live and replay. Live and replayed streams speak
   the same event contract, so this page never knows which mode produced them.
   On completion, the record is stashed and the browser moves to the report page. */

"use strict";

const MAX_TRACE_LINES = 250;
let SCENE_HEADINGS = {}; // scene_id -> heading, for narrating which scene is being read
let SCENE_TEXT = {}; // scene_id -> script text, for the hover preview
const rt = {
  built: false,
  backlog: [], // ops that arrived before the strip existed
  lastScene: {}, // desk -> scene_id
  pendingPin: {}, // desk -> pin element awaiting its flag id
  pins: {}, // flag_id -> pin element
  userScrollAt: 0,
  pinCount: 0,
};

async function loadSceneHeadings(id) {
  try {
    const res = await fetch(`/api/script/${encodeURIComponent(id)}`);
    if (!res.ok) return;
    const data = await res.json();
    for (const s of data.scenes || []) {
      SCENE_HEADINGS[s.scene_id] = s.heading;
      const [a, b] = s.raw_span || [0, 0];
      if (data.source) SCENE_TEXT[s.scene_id] = data.source.slice(a, b).trim();
    }
    buildSceneStrip(data.scenes || []);
    if (data.profile && data.profile.scene_count) renderProfile(data.profile);
  } catch {
    /* narration degrades to bare scene ids */
  }
}

/* scenePopover/hideScenePop/placeScenePop live in common.js */

function showScenePop(anchor, sid) {
  const text = SCENE_TEXT[sid];
  if (!text) return; // source not loaded (or not visible to this viewer): no popover
  clearTimeout(popHideTimer);
  const pop = scenePopover();
  pop.textContent = "";
  const head = el("div", "sp-head");
  head.appendChild(el("b", null, sid));
  head.appendChild(el("span", null, SCENE_HEADINGS[sid] || ""));
  pop.appendChild(head);
  pop.appendChild(el("pre", "sp-text", text));
  placeScenePop(pop, anchor);
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
    card.addEventListener("mouseenter", () => showScenePop(card, s.scene_id));
    card.addEventListener("mouseleave", hideScenePop);
    strip.appendChild(card);
  }
  rt.built = true;
  gState("script", "working", scenes.length + " scenes");
  const ops = rt.backlog.splice(0);
  for (const op of ops) op();
  const noteScroll = () => { rt.userScrollAt = Date.now(); };
  strip.addEventListener("wheel", noteScroll, { passive: true });
  strip.addEventListener("touchstart", noteScroll, { passive: true });
}

/* The camera never chases the desks. Only a landed finding nudges the view,
   gently, and never within 8s of the user scrolling on their own. */
function gentleFollow(node) {
  if (!node || Date.now() - (rt.userScrollAt || 0) < 8000) return;
  node.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* ---------- First Look: instant deterministic profile + unverified impressions ---------- */
function renderProfile(p) {
  const card = $("firstlook");
  if (!card) return;
  card.hidden = false;
  const stats = $("fl-stats");
  stats.textContent = "";
  const chips = [
    ["📄", p.pages, "pages · ~" + p.est_runtime_min + " min", ""],
    ["🎬", p.scene_count, "scenes · " + p.int_scenes + " INT / " + p.ext_scenes + " EXT", ""],
    ["🌙", p.night_scenes, "night scenes · " + p.night_exteriors + " night ext.", p.night_exteriors > 0 ? "fl-warn" : ""],
    ["📍", p.location_count, "locations · " + p.cast_size + " speaking parts", ""],
    ["💬", p.dialogue_pct + "%", "dialogue vs " + (100 - p.dialogue_pct) + "% action", ""],
  ];
  for (const [icon, big, small, extra] of chips) {
    const c = el("div", "fl-stat " + extra);
    c.appendChild(el("span", "fl-stat-ico", icon));
    const txt = el("div", "fl-stat-txt");
    txt.appendChild(el("b", null, String(big)));
    txt.appendChild(el("span", null, small));
    c.appendChild(txt);
    stats.appendChild(c);
  }
  if (state.mode !== "replay" && $("fl-impressions").hidden) {
    $("fl-pending").hidden = false;
    // Absolute deadline from FIRST show — profile re-renders (reconnects,
    // refreshes) used to reset the timer, so the spinner never gave up.
    if (!rt.flPendingSince) rt.flPendingSince = Date.now();
    clearTimeout(rt.flPendingTimer);
    const left = Math.max(0, 90000 - (Date.now() - rt.flPendingSince));
    rt.flPendingTimer = setTimeout(hideFlPending, left);
  }
  const lists = $("fl-lists");
  lists.textContent = "";
  const addRow = (label, items, cls) => {
    if (!items.length) return;
    const row = el("div", "fl-list");
    row.appendChild(el("b", null, label));
    const wrap = el("div", "fl-list-items");
    for (const [text, extra] of items) wrap.appendChild(el("span", extra || cls || null, text));
    row.appendChild(wrap);
    lists.appendChild(row);
  };
  addRow("Locations", (p.top_locations || []).map((l) => [`${l.name} ×${l.scenes}`]));
  addRow("Dialogue", (p.top_cast || []).map((c) => [`${c.name} · ${c.lines} lines`]));
  addRow("Elements", Object.entries(p.elements || {}).map(([name, n]) => [`${name} ×${n}`, "fl-elem"]));
}

function hideFlPending() {
  const pend = $("fl-pending");
  if (pend && $("fl-impressions").hidden) pend.hidden = true; // gave up quietly
}

function renderImpressions(d) {
  const box = $("fl-impressions");
  if (!box || !d) return;
  $("firstlook").hidden = false;
  $("fl-unverified").hidden = false;
  $("fl-pending").hidden = true;
  clearTimeout(rt.flPendingTimer);
  box.hidden = false;
  box.textContent = "";
  box.appendChild(el("p", "fl-logline", "“" + d.logline + "”"));
  box.appendChild(el("p", "fl-genre", d.genre + " · " + d.tone));
  const ul = el("ul", "fl-obs");
  for (const o of d.observations || []) ul.appendChild(el("li", null, o));
  box.appendChild(ul);
  if ((d.comps || []).length) {
    const row = el("div", "wi-comps");
    row.appendChild(el("b", "fl-comps-label", "Nearest released films:"));
    for (const c of d.comps) {
      const chip = el("span", "wi-comp");
      chip.appendChild(el("b", "wi-r r-" + c.rating, c.rating));
      chip.appendChild(document.createTextNode(`${c.title}${c.year ? " (" + c.year + ")" : ""}`));
      row.appendChild(chip);
    }
    box.appendChild(row);
  }
  if (window.FX?.on) gsap.fromTo(box, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.5 });
}

/* ---------- the agent network graph: nodes for every actor, pulses for every
   hop. Driven entirely by the same SSE events as the rest of the page. ---------- */
const SVG_NS = "http://www.w3.org/2000/svg";
const G_NODES = {
  script:      { x: 90,  y: 300, w: 120, label: "SCRIPT",            cls: "gn-script" },
  triage:      { x: 265, y: 300, w: 120, label: "Triage",            cls: "gn-triage" },
  clearance_counsel:  { x: 475, y: 90,  w: 170, label: "Clearance Counsel", cls: "gn-clearance" },
  ratings_board:      { x: 475, y: 230, w: 170, label: "Ratings Board",     cls: "gn-ratings" },
  safety_underwriter: { x: 475, y: 370, w: 170, label: "Safety Underwriter", cls: "gn-safety" },
  territory_censor:   { x: 475, y: 510, w: 170, label: "Territory Censor",  cls: "gn-territory" },
  parallel:    { x: 730, y: 60,  w: 150, label: "Parallel · web",    cls: "gn-data" },
  clickhouse:  { x: 730, y: 540, w: 150, label: `ClickHouse · ${corpusN()} films`, cls: "gn-data" },
  verifier:    { x: 730, y: 300, w: 150, label: "Blinded Verifier",  cls: "gn-verifier" },
  adjudicator: { x: 900, y: 300, w: 150, label: "Adjudicator",       cls: "gn-adj" },
};
const G_EDGES = [
  ["script", "triage"],
  ["triage", "clearance_counsel"], ["triage", "ratings_board"],
  ["triage", "safety_underwriter"], ["triage", "territory_censor"],
  ["clearance_counsel", "parallel"], ["ratings_board", "parallel"],
  ["safety_underwriter", "parallel"], ["territory_censor", "parallel"],
  ["ratings_board", "clickhouse"], ["clearance_counsel", "clickhouse"],
  ["clearance_counsel", "verifier"], ["ratings_board", "verifier"],
  ["safety_underwriter", "verifier"], ["territory_censor", "verifier"],
  ["verifier", "adjudicator"],
];
const graph = { built: false, svg: null, paths: {}, counts: {}, pulsedTriage: {} };

function gBuild() {
  const host = $("agent-graph");
  if (!host || graph.built) return;
  graph.built = true;
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 990 600");
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  for (const [a, b] of G_EDGES) {
    const na = G_NODES[a], nb = G_NODES[b];
    const pathEl = document.createElementNS(SVG_NS, "path");
    const mx = (na.x + nb.x) / 2;
    pathEl.setAttribute("d", `M ${na.x} ${na.y} C ${mx} ${na.y}, ${mx} ${nb.y}, ${nb.x} ${nb.y}`);
    pathEl.setAttribute("class", "g-edge");
    svg.appendChild(pathEl);
    graph.paths[a + ">" + b] = pathEl;
  }
  for (const [id, n] of Object.entries(G_NODES)) {
    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("class", "g-node " + n.cls);
    g.setAttribute("id", "gn-" + id);
    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("x", n.x - n.w / 2);
    rect.setAttribute("y", n.y - 26);
    rect.setAttribute("width", n.w);
    rect.setAttribute("height", 52);
    rect.setAttribute("rx", 14);
    g.appendChild(rect);
    const label = document.createElementNS(SVG_NS, "text");
    label.setAttribute("x", n.x);
    label.setAttribute("y", n.y - 2);
    label.setAttribute("class", "g-label");
    label.textContent = n.label;
    g.appendChild(label);
    const sub = document.createElementNS(SVG_NS, "text");
    sub.setAttribute("x", n.x);
    sub.setAttribute("y", n.y + 16);
    sub.setAttribute("class", "g-sub");
    sub.setAttribute("id", "gs-" + id);
    sub.textContent = "waiting";
    g.appendChild(sub);
    svg.appendChild(g);
  }
  host.appendChild(svg);
  graph.svg = svg;
  gState("script", "working", "parsing…");
}

function gState(id, state, subText) {
  const node = document.getElementById("gn-" + id);
  if (!node) return;
  node.classList.remove("g-waiting", "g-working", "g-done");
  node.classList.add("g-" + state);
  const sub = document.getElementById("gs-" + id);
  if (sub && subText != null) sub.textContent = subText;
  else if (sub && state === "working" && sub.textContent === "waiting") sub.textContent = "working";
}

function gCount(id, key, label) {
  graph.counts[key] = (graph.counts[key] || 0) + 1;
  const sub = document.getElementById("gs-" + id);
  if (sub) sub.textContent = graph.counts[key] + " " + label;
}

function gPulse(a, b, tone) {
  const pathEl = graph.paths[a + ">" + b];
  if (!pathEl || !graph.svg) return;
  pathEl.classList.add("g-hot");
  if (tone === "bad") pathEl.classList.add("g-bad");
  setTimeout(() => pathEl.classList.remove("g-hot", "g-bad"), 900);
  if (!window.FX?.on || typeof pathEl.getTotalLength !== "function") return;
  const dot = document.createElementNS(SVG_NS, "circle");
  dot.setAttribute("r", "6");
  dot.setAttribute("class", "g-dot" + (tone === "bad" ? " g-dot-bad" : ""));
  graph.svg.appendChild(dot);
  const len = pathEl.getTotalLength();
  const obj = { t: 0 };
  gsap.to(obj, {
    t: 1,
    duration: 0.8,
    ease: "power1.inOut",
    onUpdate: () => {
      const pt = pathEl.getPointAtLength(obj.t * len);
      dot.setAttribute("cx", pt.x);
      dot.setAttribute("cy", pt.y);
    },
    onComplete: () => dot.remove(),
  });
}

/* Long runs shouldn't chain the user to the tab: opt-in browser notification
   plus a tab-title flash when the report lands. */
function showLanguageCaveat() {
  if ($("lang-caveat")) return;
  const bar = $("run-status")?.closest(".card");
  if (!bar) return;
  const note = el("div", "lang-caveat");
  note.id = "lang-caveat";
  note.appendChild(el("b", null, "This script doesn't appear to be in English. "));
  note.appendChild(
    document.createTextNode(
      "The analysis is calibrated for English-language screenplays under US clearance " +
        "doctrine — findings, ratings, and costs for this script may be unreliable. " +
        "Multilingual support is on the roadmap."
    )
  );
  bar.appendChild(note);
}

function offerNotify() {
  if (!("Notification" in window) || Notification.permission === "granted") return;
  if (Notification.permission === "denied") return;
  const bar = $("run-status")?.closest(".card");
  if (!bar || $("notify-chip")) return;
  const chip = el("button", "notify-chip", "🔔 Notify me when the report is ready");
  chip.id = "notify-chip";
  chip.type = "button";
  chip.addEventListener("click", async () => {
    const perm = await Notification.requestPermission();
    chip.textContent = perm === "granted"
      ? "✓ You'll get a notification — safe to switch tabs"
      : "Notifications blocked in your browser settings";
    chip.disabled = true;
  });
  bar.appendChild(chip);
}

/* One narrated beat at a time. Events arrive in bursts no human can read, so
   beats queue and play at reading speed — slower when quiet, faster when a
   backlog builds, never a teleport. */
const NARRATORS = {
  triage: "Triage",
  verification_panel: "Verification",
  adjudicator: "Producer's desk",
};
const nowBar = { queue: [], lastAt: 0, timer: null };

function whoIs(agent) {
  const d = DESKS.find((x) => x[0] === agent);
  return d ? d[1] : NARRATORS[agent] || "";
}

function enqueueBeat(agent, text) {
  if (!text) return;
  nowBar.queue.push({ agent, text });
  if (nowBar.queue.length > 40) nowBar.queue.splice(0, nowBar.queue.length - 40);
  startBeatPlayer();
}

function beatDur() {
  return Math.max(600, Math.min(1800, Math.round(10000 / Math.max(1, nowBar.queue.length))));
}

function startBeatPlayer() {
  if (nowBar.timer) return;
  nowBar.timer = setInterval(() => {
    if (!nowBar.queue.length) return;
    if (Date.now() - nowBar.lastAt < beatDur()) return;
    nowBar.lastAt = Date.now();
    renderBeat(nowBar.queue.shift());
  }, 150);
}

function renderBeat(b) {
  const line = $("run-status");
  if (!line) return;
  const who = whoIs(b.agent);
  line.textContent = (who ? who + " · " : "") + b.text;
  if (window.FX?.on) gsap.fromTo(line, { opacity: 0.25 }, { opacity: 1, duration: 0.3, ease: "power2.out" });
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
    card.classList.add("rts-read", "glow-" + agent);
    setTimeout(() => card.classList.remove("glow-" + agent), 1800);
    rt.lastScene[agent] = sceneId;
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
    // one chip per severity+category per scene: a second finding with the same
    // label bumps a ×N counter instead of rendering a duplicate pin
    const key = severity + "|" + category;
    const existing = [...card.querySelectorAll(".rt-pin")].find((n) => n.dataset.key === key);
    if (existing) {
      const count = (parseInt(existing.dataset.count || "1", 10) || 1) + 1;
      existing.dataset.count = String(count);
      const label = existing.querySelector("span");
      if (label) label.textContent = label.dataset.base + " ×" + count;
      rt.pendingPin[agent] = existing;
      bumpPinCount(1);
      return;
    }
    const pin = el("span", `rt-pin sev-${severity}`);
    pin.dataset.key = key;
    pin.dataset.count = "1";
    pin.appendChild(el("b", null, severity));
    const label = el("span", null, prettyCat(category) + (ids.length > 1 ? ` +${ids.length - 1}` : ""));
    label.dataset.base = label.textContent;
    pin.appendChild(label);
    card.querySelector(".rts-pins").appendChild(pin);
    rt.pendingPin[agent] = pin;
    if (window.FX?.on) {
      gsap.fromTo(pin, { scale: 0, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.45, ease: "back.out(1.8)" });
    }
    bumpPinCount(1);
    gentleFollow(card);
  });
}

function bumpPinCount(delta) {
  rt.pinCount = Math.max(0, (rt.pinCount || 0) + delta);
  const sc = $("strip-count");
  if (sc) sc.textContent = rt.pinCount ? rt.pinCount + (rt.pinCount === 1 ? " finding pinned" : " findings pinned") : "";
}

function assignPinId(agent, brief) {
  const m = (brief || "").match(/F\d+/);
  rtOp(() => {
    const pin = rt.pendingPin[agent];
    if (!pin) return;
    delete rt.pendingPin[agent];
    if (m) {
      rt.pins[m[0]] = pin;
    } else {
      const count = parseInt(pin.dataset.count || "1", 10) || 1;
      if (count > 1) {
        pin.dataset.count = String(count - 1);
        const label = pin.querySelector("span");
        if (label) label.textContent = count - 1 > 1 ? label.dataset.base + " ×" + (count - 1) : label.dataset.base;
      } else {
        pin.remove(); // the filing was rejected by validation — never landed
      }
      bumpPinCount(-1);
    }
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

/* The triage call is one long model request with no visible output — without
   a heartbeat the page looks dead for minutes on a feature. */
const TRIAGE_BEATS = [
  "Triage is reading the entire script in a single pass…",
  "Extracting every clearance-relevant entity — people, brands, songs, hazards…",
  "Deciding which desk owns each finding-to-be…",
  "Building the four desks' worklists — the desks open the moment they land…",
  "Still reading — a feature-length script takes a few minutes to absorb…",
];
let triageTicker = null;
let triageBeatIdx = 0;

function startTriageTicker() {
  stopTriageTicker();
  triageTicker = setInterval(() => {
    enqueueBeat("triage", TRIAGE_BEATS[triageBeatIdx % TRIAGE_BEATS.length]);
    triageBeatIdx += 1;
  }, 9000);
}

function stopTriageTicker() {
  if (triageTicker) {
    clearInterval(triageTicker);
    triageTicker = null;
  }
}

const PHASE_BEATS = {
  triage: "Reading the script and building each desk's worklist…",
  desks: "The four desks take the script — each investigates on its own.",
  verify: "Every filed finding now faces a blinded verifier.",
  adjudicate: "The producer's desk reconciles the four reports.",
};

function setPhase(name) {
  const idx = PHASE_ORDER.indexOf(name);
  if (idx < 0 || idx < PHASE_ORDER.indexOf(state.phase)) return;
  if (name !== state.phase && PHASE_BEATS[name]) enqueueBeat("system", PHASE_BEATS[name]);
  if (idx >= PHASE_ORDER.indexOf("verify")) hideFlPending();
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

const DESK_SHORT = {
  clearance_counsel: "Clearance",
  ratings_board: "Ratings",
  safety_underwriter: "Safety",
  territory_censor: "Territory",
};

function buildFeedChips() {
  const wrap = $("feeds-chips");
  if (!wrap) return;
  wrap.textContent = "";
  for (const [id] of DESKS) {
    const chip = el("span", "fc fc-" + id);
    chip.id = "fc-" + id;
    chip.appendChild(el("span", "fc-dot"));
    chip.appendChild(el("b", null, DESK_SHORT[id] || id));
    chip.appendChild(el("span", "fc-count", "waiting"));
    wrap.appendChild(chip);
  }
}

function buildPanel() {
  gBuild();
  buildFeedChips();
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
  const fc = document.querySelector(`#fc-${id} .fc-count`);
  if (fc) {
    fc.textContent = d.done
      ? `✓ ${d.flags} ${d.flags === 1 ? "flag" : "flags"}`
      : d.started
        ? `${d.flags} ${d.flags === 1 ? "flag" : "flags"} so far`
        : "waiting";
    $("fc-" + id)?.classList.toggle("fc-working", d.started && !d.done);
    $("fc-" + id)?.classList.toggle("fc-done", d.done);
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
  enqueueBeat(agent, text);
}

function handleDeskEvent(ev) {
  const d = state.desks[ev.agent];
  if (!d) return;
  stopTriageTicker();
  if (!d.started && !graph.pulsedTriage[ev.agent]) {
    graph.pulsedTriage[ev.agent] = true;
    gPulse("triage", ev.agent);
    gState("triage", "done", "worklists out");
    gState(ev.agent, "working");
  }
  d.started = true;
  if (ev.type === "tool_call") {
    d.calls += 1;
    const a = ev.args || {};
    if (ev.tool === "read_scene") moveDeskDot(ev.agent, a.scene_id);
    else if (ev.tool === "research") {
      rippleScene(ev.agent, trim(a.objective, 80));
      gPulse(ev.agent, "parallel");
      gCount("parallel", "research", "searches");
    } else if (ev.tool === "query_precedent") {
      gPulse(ev.agent, "clickhouse");
      gCount("clickhouse", "precedent", "queries");
    } else if (ev.tool === "file_flag") {
      dropPin(ev.agent, a.severity || "FYI", a.category, a.scene_ids);
      gPulse(ev.agent, "verifier");
    }
    if (ev.tool === "read_scene") setDeskSpotlight(ev.agent, `Now reading ${sceneLabel(a.scene_id)}`);
    else if (ev.tool === "research") setDeskSpotlight(ev.agent, `Researching: ${trim(a.objective, 60)}`);
    else if (ev.tool === "query_precedent") setDeskSpotlight(ev.agent, "Consulting released-film comparables…");
    else if (ev.tool === "file_flag") setDeskSpotlight(ev.agent, `Filed ${a.severity || ""} — ${prettyCat(a.category)}`);
  }
  if (ev.type === "tool_result" && ev.tool === "file_flag") {
    assignPinId(ev.agent, ev.brief);
    // count FILINGS, not attempts — a provenance-rejected try is not a flag
    if (/Filed F\d+/.test(ev.brief || "")) {
      d.flags += 1;
      gCount("verifier", "filed", "to verify");
      const gsub = document.getElementById("gs-" + ev.agent);
      if (gsub) gsub.textContent = d.flags + " flags";
    }
  }
  if (ev.type === "text" && /^done\b/i.test(ev.text || "")) {
    d.done = true;
    setDeskSpotlight(ev.agent, "Desk closed.");
    gState(ev.agent, "done", d.flags + " flags filed");
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
    gState("verifier", "working");
    gPulse("verifier", "adjudicator", verdict === "REJECTED" || verdict === "UNSUPPORTED" ? "bad" : "ok");
    gCount("adjudicator", "verdicts", "verdicts in");
    enqueueBeat("verification_panel", `${fid} ${prettyCat(cat)} — ${verdict}`);
    return true;
  }
  if (ev.type === "tool_result" && ev.tool === "verify_flag") {
    const m = (ev.brief || "").match(/^(F\d+)\s*·\s*(\w+)\s*(?:—\s*(.*))?$/);
    if (m) {
      studioCard(m[1], "", "FYI", m[2], m[3] || "");
      pinVerdict(m[1], m[2]);
      gState("verifier", "working");
      gPulse("verifier", "adjudicator", m[2] === "REJECTED" || m[2] === "UNSUPPORTED" ? "bad" : "ok");
      gCount("adjudicator", "verdicts", "verdicts in");
      enqueueBeat("verification_panel", `${m[1]} — ${m[2]}`);
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

function startClock(startedAtEpoch) {
  // a rejoin anchors to the run's TRUE start — the timer must never lie 00:00
  state.startedAt = startedAtEpoch ? startedAtEpoch * 1000 : Date.now();
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
      if (!rt.built) loadSceneHeadings(state.reportId); // usually pre-fetched from the URL
      $("run-title").textContent = ev.script_title || "Analysis";
      const chip = $("mode-chip");
      chip.textContent = ev.mode === "replay" ? "Replay · recorded run" : "Live";
      chip.className = "chip " + (ev.mode === "replay" ? "replay" : "live");
      startClock(ev.mode === "replay" ? null : ev.started_at);
      setPhase("triage");
      bumpProgress();
      if (ev.mode !== "replay") {
        startTriageTicker();
        offerNotify();
        if (ev.english_ok === false) showLanguageCaveat();
      }
      break;
    }
    case "first_look":
      renderImpressions(ev.data);
      break;
    case "tool_call":
    case "tool_result":
    case "text":
      noteActivity(ev);
      if (DESK_IDS.includes(ev.agent)) {
        setPhase("desks");
        handleDeskEvent(ev);
      } else {
        if (ev.agent === "verification_panel") setPhase("verify");
        else if (ev.agent === "adjudicator") {
          setPhase("adjudicate");
          gState("verifier", "done");
          gState("adjudicator", "working", "reconciling");
        } else if (ev.agent === "triage") {
          gState("triage", "working", "reading script");
        }
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

function sweepSceneStates() {
  rtOp(() => {
    document.querySelectorAll(".rt-scene").forEach((card) => {
      const pins = card.querySelector(".rts-pins");
      if (pins && pins.childElementCount > 0) return;
      const head = card.querySelector(".rts-head");
      if (head && !card.querySelector(".rts-clear")) head.appendChild(el("span", "rts-clear", "no flags"));
    });
  });
}

function announceDone(record) {
  const title = (record && record.script_title) || "Your analysis";
  document.title = "✓ Report ready — ScriptRisk";
  if ("Notification" in window && Notification.permission === "granted") {
    try {
      new Notification("ScriptRisk — report ready", {
        body: title + " has finished analysis. Opening your report.",
        icon: "/apple-touch-icon.png",
      });
    } catch { /* notification is a courtesy, never an error */ }
  }
}

function onResult(record) {
  state.gotResult = true;
  announceDone(record);
  sweepSceneStates();
  gState("script", "done");
  gState("adjudicator", "done", "report ready");
  for (const id of ["verifier", "triage", ...DESK_IDS]) gState(id, "done");
  nowBar.queue.length = 0;
  renderBeat({ agent: "system", text: "Done — your marked-up script is ready. Opening the report…" });
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
      colors: ["#e8b64c", "#f4cd66", "#a5b4fc", "#fcd34d", "#7dd3fc"],
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

function wireFirstLookCollapse() {
  const btn = $("fl-collapse");
  const card = $("firstlook");
  if (!btn || !card) return;
  const apply = (min) => {
    card.classList.toggle("fl-min", min);
    btn.textContent = min ? "Show" : "Hide";
    try { sessionStorage.setItem("fl-min", min ? "1" : ""); } catch (e) { /* fine */ }
  };
  let min = false;
  try { min = sessionStorage.getItem("fl-min") === "1"; } catch (e) { /* fine */ }
  apply(min);
  btn.addEventListener("click", () => apply(!card.classList.contains("fl-min")));
}

document.addEventListener("DOMContentLoaded", () => {
  wireFirstLookCollapse();
  const toggleFeeds = () => {
    const body = $("feeds-body");
    if (!body) return;
    const hidden = body.classList.toggle("hidden");
    $("feeds-toggle").textContent = hidden ? "Show" : "Hide";
  };
  $("feeds-head")?.addEventListener("click", toggleFeeds);
  $("feeds-head")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleFeeds(); }
  });
  if (new URLSearchParams(window.location.search).get("feeds") === "1") toggleFeeds();
  $("studio-toggle")?.addEventListener("click", () => {
    const body = $("studio-body");
    const hidden = body.classList.toggle("hidden");
    $("studio-toggle").textContent = hidden ? "Show" : "Hide";
  });
  const params = new URLSearchParams(window.location.search);
  const liveId = params.get("id");
  if (liveId) loadSceneHeadings(liveId); // profile + strip render before the stream even opens
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

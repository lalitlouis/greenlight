/* Writer's Room page: upload -> poll /api/writer/{id} -> render the three desks.
   ?run=latest (or a writer_* id) renders a recorded example directly. */

"use strict";

const POLL_MS = 1500;
// Transient blips (redeploy, cold start, network) get retries; only give up
// after several. These three were REFERENCED by poll() but never declared —
// under "use strict" the first successful poll threw ReferenceError, the catch
// threw again, and the progress screen froze forever with no error shown. The
// whole page was dead on every path.
const POLL_MAX_MISSES = 5;
let pollMisses = 0;

function progressFailed(message) {
  clearInterval(progressTimer);
  const title = $("wr-progress-title");
  if (title) title.textContent = "That run did not finish";
  const bar = $("wr-bar-fill");
  if (bar) bar.style.width = "0%";
  const pct = $("wr-pct");
  if (pct) pct.textContent = "—";
  toast(message, true);
}

async function uploadForWriter(file) {
  showUploadOverlay(file);
  try {
    const { run_id } = await uploadWithProgress("/api/writer", file);
    hideUploadOverlay();
    showProgress();
    poll(run_id);
  } catch (e) {
    hideUploadOverlay();
    if (e.status === 401) {
      toSignIn();
      return;
    }
    toast("upload failed: " + e.message, true);
  }
}

let progressStart = null;
let progressTimer = null;
let deskStageStart = null;
const DESK_STAGE_S = 55; // typical read; the bar eases across this stage's span only

// Real checkpoints from the server; percent is anchored to truth at each stage.
const STAGE_PCT = { upload: 4, parsed: 12, format_done: 18, desks: 20, comps: 88, done: 100 };
const STAGE_ORDER = ["upload", "parsed", "format_done", "desks", "comps"];

function showProgress() {
  $("writer-intake").classList.add("hidden");
  $("writer-progress").classList.remove("hidden");
  progressStart = Date.now();
  clearInterval(progressTimer);
  progressTimer = setInterval(renderProgress, 1000);
}

let currentStage = "upload";
let currentInfo = {};
const stageInfos = {};

function setStage(stage, info) {
  if (STAGE_ORDER.indexOf(stage) < STAGE_ORDER.indexOf(currentStage)) return;
  if (stage === "desks" && currentStage !== "desks") deskStageStart = Date.now();
  currentStage = stage;
  currentInfo = info || {};

  const pi = stageInfos.parsed || {};
  const fi = stageInfos.format_done || {};
  const texts = {
    upload: ["Received."],
    parsed: [
      pi.scenes != null
        ? `${pi.title || "Screenplay"} — ${pi.scenes} scenes, ~${pi.pages} pages.`
        : "Parsed.",
    ],
    format_done: [
      fi.passes != null
        ? `${fi.passes} checks passed, ${fi.warns} warning${fi.warns === 1 ? "" : "s"} — ready in the report.`
        : "Done — results in the report.",
    ],
    desks: ["Both desks are reading now — long thoughts are normal…"],
    comps: ["Embedding your synopsis and searching the corpus…"],
  };
  const idx = STAGE_ORDER.indexOf(stage);
  document.querySelectorAll("#wr-stages li").forEach((li) => {
    const liIdx = STAGE_ORDER.indexOf(li.dataset.stage);
    li.classList.toggle("done", liIdx < idx || stage === "done");
    li.classList.toggle("active", liIdx === idx && stage !== "done");
  });
  for (const [s, lines] of Object.entries(texts)) {
    const node = $("ws-" + (s === "format_done" ? "format" : s));
    if (node && STAGE_ORDER.indexOf(s) <= idx) node.textContent = lines[0];
  }
}

function renderProgress() {
  const s = (Date.now() - progressStart) / 1000;
  let pct = STAGE_PCT[currentStage] ?? 4;
  if (currentStage === "desks" && deskStageStart) {
    const ds = (Date.now() - deskStageStart) / 1000;
    pct += Math.min(0.95, ds / DESK_STAGE_S) * (STAGE_PCT.comps - STAGE_PCT.desks);
  }
  const fill = $("wr-bar-fill");
  if (fill) fill.style.width = pct.toFixed(1) + "%";
  const pctNode = $("wr-pct");
  if (pctNode) pctNode.textContent = Math.round(pct) + "%";
  const elapsed = $("wr-elapsed");
  if (elapsed) elapsed.textContent = `${Math.floor(s)}s`;
}

async function poll(runId) {
  try {
    const res = await fetch(`/api/writer/${encodeURIComponent(runId)}`);
    if (!res.ok) throw new Error(`run not found (${res.status})`);
    pollMisses = 0;
    const body = await res.json();
    if (body.stages) {
      for (const [s, info] of Object.entries(body.stages)) stageInfos[s] = info;
    }
    if (body.stage) setStage(body.stage, body.stage_info);
    if (body.status === "running") {
      setTimeout(() => poll(runId), POLL_MS);
      return;
    }
    if (body.status === "error" && !body.record) {
      progressFailed(body.message || "unknown error");
      return;
    }
    setStage("comps", {});
    const fill = $("wr-bar-fill");
    if (fill) fill.style.width = "100%";
    const pctNode = $("wr-pct");
    if (pctNode) pctNode.textContent = "100%";
    clearInterval(progressTimer);
    render(body.record);
  } catch (e) {
    // Transient blips (redeploy, network) get retries; only give up after several.
    pollMisses += 1;
    if (pollMisses >= POLL_MAX_MISSES) {
      progressFailed(e.message + " — please upload again.");
    } else {
      setTimeout(() => poll(runId), POLL_MS * 2);
    }
  }
}

/* ---------------- render ---------------- */

const VERDICT_TONE = { RECOMMEND: "good", CONSIDER: "mid", PASS: "bad" };

function sceneChips(ids) {
  const wrap = el("span", "wr-chips");
  for (const sid of ids || []) wrap.appendChild(el("span", "scene-link", sid));
  return wrap;
}

function render(record) {
  $("writer-intake").classList.add("hidden");
  $("writer-progress").classList.add("hidden");
  const root = $("writer-result");
  root.textContent = "";
  root.classList.remove("hidden");

  const head = el("div", "section-head");
  head.appendChild(el("h2", null, record.script_title || "Your screenplay"));
  root.appendChild(head);

  const cov = record.coverage;
  if (cov) {
    const card = el("div", "card wr-card");
    const top = el("div", "wr-card-head");
    top.appendChild(el("h3", null, "Coverage"));
    const v = el("span", "verdict-badge vb-" + (VERDICT_TONE[cov.verdict] || "mid"), cov.verdict);
    top.appendChild(v);
    card.appendChild(top);
    card.appendChild(el("p", "wr-verdict-reason", cov.verdict_reason || ""));

    card.appendChild(el("div", "blk-label", "Logline, as read"));
    card.appendChild(el("p", "wr-logline", cov.logline_as_read || ""));
    card.appendChild(el("div", "blk-label", "Synopsis"));
    card.appendChild(el("p", null, cov.synopsis || ""));

    const cols = el("div", "wr-notes");
    const mk = (title, items, cls) => {
      const col = el("div", "wr-note-col " + cls);
      col.appendChild(el("h4", null, title));
      for (const n of items || []) {
        const li = el("div", "wr-note");
        li.appendChild(sceneChips(n.scene_ids));
        li.appendChild(el("p", null, n.note));
        col.appendChild(li);
      }
      return col;
    };
    cols.appendChild(mk("What works", cov.strengths, "good"));
    cols.appendChild(mk("What needs work", cov.weaknesses, "bad"));
    card.appendChild(cols);

    if ((cov.character_notes || []).length) {
      card.appendChild(el("div", "blk-label", "Characters"));
      const ul = el("ul", "plain-list");
      for (const n of cov.character_notes) ul.appendChild(el("li", null, n));
      card.appendChild(ul);
    }
    const extras = el("p", "wr-extras");
    if (cov.dialogue_note) extras.appendChild(el("span", null, "Dialogue — " + cov.dialogue_note + " "));
    if (cov.pacing_note) extras.appendChild(el("span", null, "Pacing — " + cov.pacing_note));
    card.appendChild(extras);
    root.appendChild(card);
  }

  const pitch = record.pitch;
  if (pitch) {
    const card = el("div", "card wr-card");
    const top = el("div", "wr-card-head");
    top.appendChild(el("h3", null, "Pitch package"));
    top.appendChild(el("span", "wr-genre", [pitch.genre, pitch.tone].filter(Boolean).join(" · ")));
    card.appendChild(top);

    card.appendChild(el("div", "blk-label", "Logline options"));
    const ol = el("ol", "wr-loglines");
    for (const l of pitch.logline_options || []) ol.appendChild(el("li", null, l));
    card.appendChild(ol);

    if ((pitch.comps || []).length) {
      card.appendChild(
        el("div", "blk-label", "Comparables — retrieved from released films, with sources")
      );
      const comps = el("div", "comps");
      for (const c of pitch.comps) {
        const row = el("div", "comp-row");
        row.appendChild(el("b", "comp-rating r-" + c.rating, c.rating));
        const main = el("div", "comp-main");
        main.appendChild(el("span", "comp-title", `${c.title}${c.year ? " (" + c.year + ")" : ""}`));
        if (c.blurb) main.appendChild(el("span", "comp-quote", c.blurb));
        const compUrl = safeUrl(c.source_url);
        if (compUrl) {
          const a = el("a", "comp-src", "source");
          a.href = compUrl;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          main.appendChild(a);
        }
        row.appendChild(main);
        comps.appendChild(row);
      }
      card.appendChild(comps);
    }

    card.appendChild(el("div", "blk-label", "One-page synopsis"));
    for (const para of (pitch.one_page_synopsis || "").split(/\n\n+/)) {
      card.appendChild(el("p", null, para));
    }
    const meta = el("p", "wr-extras");
    if (pitch.target_audience) meta.appendChild(el("span", null, "Audience — " + pitch.target_audience + " "));
    if (pitch.why_now) meta.appendChild(el("span", null, "Why now — " + pitch.why_now));
    card.appendChild(meta);
    root.appendChild(card);
  }

  const fmt = record.format;
  if (fmt) {
    const card = el("div", "card wr-card");
    const top = el("div", "wr-card-head");
    top.appendChild(el("h3", null, "Format & readiness"));
    top.appendChild(
      el(
        "span",
        "wr-genre",
        `${fmt.stats.pages} pp · ${fmt.stats.scenes} scenes · ${fmt.stats.cast} speaking roles`
      )
    );
    card.appendChild(top);
    const list = el("div", "wr-checks");
    for (const c of fmt.checks || []) {
      const row = el("div", "wr-check st-" + c.status);
      row.appendChild(el("span", "wr-check-mark", c.status === "PASS" ? "✓" : c.status === "WARN" ? "!" : "i"));
      const body = el("div");
      body.appendChild(el("b", null, c.label));
      body.appendChild(el("p", null, c.detail));
      row.appendChild(body);
      list.appendChild(row);
    }
    card.appendChild(list);
    root.appendChild(card);
  }

  const cta = el("div", "report-actions");
  const again = el("button", "btn btn-primary", "Read another screenplay");
  again.type = "button";
  again.addEventListener("click", promptUpload2);
  cta.appendChild(again);
  const clearance = el("a", "btn btn-secondary", "Now run the clearance desks →");
  clearance.href = "/home";
  cta.appendChild(clearance);
  root.appendChild(cta);

  window.FX?.reveals(root);
  window.FX?.staggerIn(root.querySelectorAll(".wr-card"));
}

/* dedicated picker: the nav CTA routes to the clearance pipeline; this one stays here */
function promptUpload2() {
  if (!requireSignIn()) return;
  openUploadModal({
    title: "Writer's Room — read my screenplay",
    note: "Fountain, plain text, or PDF · coverage, pitch, and format check in one pass",
    action: "Start the read",
    onFile: uploadForWriter,
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  $("writer-upload")?.addEventListener("click", promptUpload2);
  const runId = new URLSearchParams(window.location.search).get("run");
  if (runId) {
    showProgress();
    poll(runId);
  }
});

/* Writer's Room page: upload -> poll /api/writer/{id} -> render the three desks.
   ?run=latest (or a writer_* id) renders a recorded example directly. */

"use strict";

const POLL_MS = 3000;

async function uploadForWriter(file) {
  showUploadOverlay(file);
  try {
    const { run_id } = await uploadWithProgress("/api/writer", file);
    hideUploadOverlay();
    showProgress();
    poll(run_id);
  } catch (e) {
    hideUploadOverlay();
    toast("upload failed: " + e.message, true);
  }
}

let progressStart = null;
let progressTimer = null;
const WR_EXPECTED_S = 80; // typical room read; the bar eases toward 92% and waits

function showProgress() {
  $("writer-intake").classList.add("hidden");
  $("writer-progress").classList.remove("hidden");
  progressStart = Date.now();
  clearInterval(progressTimer);
  progressTimer = setInterval(() => {
    const s = (Date.now() - progressStart) / 1000;
    const pct = Math.min(92, (s / WR_EXPECTED_S) * 100);
    const fill = $("wr-bar-fill");
    if (fill) fill.style.width = pct.toFixed(1) + "%";
    const elapsed = $("wr-elapsed");
    if (elapsed) elapsed.textContent = `${Math.floor(s)}s`;
    const steps = [
      [0, "Format check complete — it runs instantly."],
      [8, "Coverage desk is reading your script…"],
      [25, "Pitch desk is drafting loglines and the synopsis…"],
      [45, "Matching your story against 2,487 released films…"],
      [70, "Almost there — assembling the three reports…"],
    ];
    const line = steps.filter(([at]) => s >= at).pop();
    const status = $("wr-progress-line");
    if (status && line) status.textContent = line[1];
  }, 1000);
}

let pollMisses = 0;
const POLL_MAX_MISSES = 5;

function progressFailed(message) {
  clearInterval(progressTimer);
  $("writer-progress").classList.add("hidden");
  $("writer-intake").classList.remove("hidden");
  toast("Writer's Room failed: " + message, true);
}

async function poll(runId) {
  try {
    const res = await fetch(`/api/writer/${encodeURIComponent(runId)}`);
    if (!res.ok) throw new Error(`run not found (${res.status})`);
    pollMisses = 0;
    const body = await res.json();
    if (body.status === "running") {
      setTimeout(() => poll(runId), POLL_MS);
      return;
    }
    if (body.status === "error" && !body.record) {
      progressFailed(body.message || "unknown error");
      return;
    }
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
        if (c.source_url) {
          const a = el("a", "comp-src", "source");
          a.href = c.source_url;
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
  let input = $("wr-file-input");
  if (!input) {
    input = el("input");
    input.type = "file";
    input.accept = ".fountain,.txt,.pdf,text/plain,application/pdf";
    input.id = "wr-file-input";
    input.hidden = true;
    input.addEventListener("change", (e) => {
      if (e.target.files[0]) uploadForWriter(e.target.files[0]);
    });
    document.body.appendChild(input);
  }
  input.click();
}

document.addEventListener("DOMContentLoaded", async () => {
  $("writer-upload")?.addEventListener("click", promptUpload2);
  const runId = new URLSearchParams(window.location.search).get("run");
  if (runId) {
    showProgress();
    poll(runId);
  }
});

/* Home page: recent analyses grid from GET /api/runs. */

"use strict";

function scoreTone(score, blockers) {
  if (score == null) return "";
  return blockers > 0 || score < 40 ? "bad" : score < 75 ? "mid" : "good";
}

async function loadRuns() {
  const grid = $("runs-grid");
  try {
    const res = await fetch("/api/runs");
    const runs = await res.json();
    grid.textContent = "";
    if (!runs.length) {
      grid.appendChild(
        el("div", "card runs-empty", "No analyses yet — upload a screenplay to start one.")
      );
      return;
    }
    for (const r of runs.slice(0, 9)) {
      const card = el("a", "card run-card");
      card.href = `/report?run=${encodeURIComponent(r.id)}`;
      const top = el("div", "rc-top");
      const title = el("span", "rc-title", r.title || r.id);
      top.appendChild(title);
      if (r.score != null) {
        top.appendChild(el("span", "score-pill " + scoreTone(r.score, r.blockers), `${r.score}/100`));
      }
      card.appendChild(top);
      const stats = el("div", "rc-stats");
      const s1 = el("span");
      s1.appendChild(el("b", null, String(r.flags)));
      s1.appendChild(document.createTextNode(" findings"));
      stats.appendChild(s1);
      if (r.rejected) {
        const s2 = el("span");
        s2.appendChild(el("b", null, String(r.rejected)));
        s2.appendChild(document.createTextNode(" rejected in verification"));
        stats.appendChild(s2);
      }
      if (r.predicted_rating) {
        const s3 = el("span");
        s3.appendChild(document.createTextNode("predicted "));
        s3.appendChild(el("b", null, r.predicted_rating));
        stats.appendChild(s3);
      }
      card.appendChild(stats);
      const bottom = el("div", "rc-top");
      bottom.appendChild(el("span", "rc-when", fmtDate(r.generated_at)));
      if (r.demo) bottom.appendChild(el("span", "demo-tag", "DEMO RECORD"));
      card.appendChild(bottom);
      grid.appendChild(card);
    }
    window.FX?.staggerIn(grid.querySelectorAll(".run-card"));
  } catch {
    grid.textContent = "";
    grid.appendChild(el("div", "card runs-empty", "Could not load analyses."));
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadRuns();
  $("hero-upload")?.addEventListener("click", promptUpload);
  $("band-upload")?.addEventListener("click", promptUpload);
  window.FX?.hero();
  window.FX?.reveals();
  window.FX?.counters();
});

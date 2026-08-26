/* Case studies index: famous screenplays through the pipeline, script text never shipped. */

"use strict";

function caseTone(score, blockers) {
  if (score == null) return "";
  return blockers > 0 || score < 40 ? "bad" : score < 75 ? "mid" : "good";
}

async function loadCases() {
  const grid = document.getElementById("cases-grid");
  try {
    const res = await fetch("/api/cases");
    const cases = await res.json();
    grid.textContent = "";
    if (!cases.length) {
      grid.appendChild(el("div", "card runs-empty", "Case studies are on the way."));
      return;
    }
    for (const c of cases) {
      const card = el("a", "card case-card");
      const slugs = { case_reservoir_dogs: "reservoir-dogs", case_clerks: "clerks", case_little_miss_sunshine: "little-miss-sunshine" };
      card.href = slugs[c.id] ? `/cases/${slugs[c.id]}` : `/report?run=${encodeURIComponent(c.id)}`;
      const top = el("div", "rc-top");
      top.appendChild(el("span", "case-title", `${c.title} (${c.year})`));
      if (c.score != null) {
        top.appendChild(el("span", "score-pill " + caseTone(c.score, c.blockers), `${c.score}/100`));
      }
      card.appendChild(top);
      card.appendChild(el("p", "case-hook-line", c.hook || ""));
      const stats = el("div", "rc-stats");
      const s1 = el("span");
      s1.appendChild(el("b", null, String(c.flags)));
      s1.appendChild(document.createTextNode(" findings"));
      stats.appendChild(s1);
      if (c.predicted_rating) {
        const s2 = el("span");
        s2.appendChild(document.createTextNode("predicted "));
        s2.appendChild(el("b", null, c.predicted_rating));
        if (c.target_rating && c.target_rating !== c.predicted_rating) {
          s2.appendChild(document.createTextNode(` vs ${c.target_rating} target`));
        }
        stats.appendChild(s2);
      }
      if (c.rejected) {
        const s3 = el("span");
        s3.appendChild(el("b", null, String(c.rejected)));
        s3.appendChild(document.createTextNode(" rejected by the verifier"));
        stats.appendChild(s3);
      }
      card.appendChild(stats);
      card.appendChild(el("span", "stage-cta", "Read the report →"));
      grid.appendChild(card);
    }
    window.FX?.staggerIn(grid.querySelectorAll(".case-card"));
  } catch {
    grid.textContent = "";
    grid.appendChild(el("div", "card runs-empty", "Could not load case studies."));
  }
}

document.addEventListener("DOMContentLoaded", loadCases);

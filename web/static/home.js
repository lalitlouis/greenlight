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

async function loadHomeCases() {
  const grid = $("home-cases");
  if (!grid) return;
  try {
    const cases = await (await fetch("/api/cases")).json();
    grid.textContent = "";
    if (!cases.length) {
      grid.closest("section")?.classList.add("hidden");
      return;
    }
    for (const c of cases.slice(0, 3)) {
      const card = el("a", "card case-card");
      card.href = `/report?run=${encodeURIComponent(c.id)}`;
      const top = el("div", "rc-top");
      top.appendChild(el("span", "case-title", `${c.title} (${c.year})`));
      if (c.score != null) top.appendChild(el("span", "score-pill bad", `${c.score}/100`));
      card.appendChild(top);
      card.appendChild(el("p", "case-hook-line", c.hook || ""));
      card.appendChild(el("span", "stage-cta", "Read the report →"));
      grid.appendChild(card);
    }
    window.FX?.staggerIn(grid.querySelectorAll(".case-card"));
  } catch {
    grid.closest("section")?.classList.add("hidden");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadRuns();
  loadHomeCases();
  $("hero-upload")?.addEventListener("click", promptUpload);
  $("band-upload")?.addEventListener("click", promptUpload);
  window.FX?.hero();
  window.FX?.reveals();
  window.FX?.counters();
});

/* ---------- showcase carousel ---------- */
const SLIDES = [
  ["reject", "<b>The cross-examination.</b> A blinded verifier challenges every finding — here it REJECTS F201, whose source didn't support the claim. Rejected flags never reach the report."],
  ["report", "<b>The verdict, with the money.</b> Not cleared — 2 blockers, 21 findings, $184,500–$822,500 of estimated clearance exposure, priced finding by finding."],
  ["read", "<b>The analysis, live on your script.</b> Four desks read concurrently; findings pin to their scenes the moment they're filed."],
  ["citation", "<b>Receipts, not opinions.</b> Every finding quotes its sources verbatim — a flag without a citation is structurally impossible."],
  ["rating", "<b>Your rating, predicted from evidence.</b> Seven of the eight nearest released comparables are rated R — with sources for each."],
  ["script", "<b>The marked-up script.</b> Every finding anchored to its scene in the margin, severity-tagged, one click from note to full report."],
];

function initCarousel() {
  const img = $("car-img");
  if (!img) return;
  const caption = $("car-caption");
  const dots = $("car-dots");
  let i = 0;
  let timer = null;

  // preload so arrow clicks are instant
  for (const [name] of SLIDES) new Image().src = `/static/shots/${name}.webp`;

  SLIDES.forEach((_, n) => {
    const d = el("button", "car-dot" + (n === 0 ? " active" : ""));
    d.type = "button";
    d.setAttribute("aria-label", `Slide ${n + 1}`);
    d.addEventListener("click", () => show(n, true));
    dots.appendChild(d);
  });

  function show(n, manual) {
    i = (n + SLIDES.length) % SLIDES.length;
    img.classList.add("fading");
    setTimeout(() => {
      img.src = `/static/shots/${SLIDES[i][0]}.webp`;
      caption.innerHTML = SLIDES[i][1];
      img.classList.remove("fading");
    }, 180);
    dots.querySelectorAll(".car-dot").forEach((d, n2) => d.classList.toggle("active", n2 === i));
    if (manual) restart(12000); // a person is reading — slow down
  }

  function restart(delay) {
    clearInterval(timer);
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    timer = setInterval(() => show(i + 1), delay || 6500);
  }

  $("car-prev").addEventListener("click", () => show(i - 1, true));
  $("car-next").addEventListener("click", () => show(i + 1, true));
  const box = $("shot-carousel");
  box.addEventListener("mouseenter", () => clearInterval(timer));
  box.addEventListener("mouseleave", () => restart());
  let x0 = null;
  box.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; }, { passive: true });
  box.addEventListener("touchend", (e) => {
    if (x0 == null) return;
    const dx = e.changedTouches[0].clientX - x0;
    if (Math.abs(dx) > 45) show(i + (dx < 0 ? 1 : -1), true);
    x0 = null;
  }, { passive: true });

  caption.innerHTML = SLIDES[0][1];
  restart();
}

initCarousel();

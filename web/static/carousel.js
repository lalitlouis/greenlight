/* Product showcase carousel — lives on How it works. Requires common.js ($, el). */

"use strict";

/* ---------- showcase carousel ---------- */
const SLIDES = [
  ["reject", "<b>The cross-examination.</b> A blinded verifier challenges every finding — the REJECTED verdict here is a flag whose source didn't support the claim. Rejected flags never reach the report."],
  ["report", "<b>The verdict, with the money.</b> Not cleared — 2 blockers, 21 findings, $104,500–$413,500 of estimated clearance exposure, priced finding by finding."],
  ["read", "<b>The analysis, live on your script.</b> Four desks read concurrently; findings pin to their scenes the moment they're filed."],
  ["citation", "<b>Receipts, not opinions.</b> Every finding quotes its sources verbatim — a flag without a citation is structurally impossible."],
  ["rating", "<b>Your rating, predicted from evidence.</b> Five of the eight nearest released comparables are rated R — with sources for each."],
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

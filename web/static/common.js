/* SCRIPTRISK shared chrome + helpers. Every page includes this first.
   The header/footer are injected here so seven pages stay consistent without a
   build step. Vanilla JS, no CDN, works offline. */

"use strict";

const SEVS = ["BLOCKER", "HIGH", "MEDIUM", "LOW", "FYI"];
const DESKS = [
  ["clearance_counsel", "Clearance Counsel", "Rights & clearances"],
  ["ratings_board", "Ratings Board", "MPA rating drivers"],
  ["safety_underwriter", "Safety Underwriter", "Physical production risk"],
  ["territory_censor", "Territory Censor", "US · UK · CN · UAE"],
];
const DESK_IDS = DESKS.map((d) => d[0]);

const $ = (id) => document.getElementById(id);

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function money(range) {
  if (!range || range.length < 2) return null;
  const f = (n) => "$" + Math.round(n).toLocaleString("en-US");
  return `${f(range[0])}–${f(range[1])}`;
}

function prettyCat(cat) {
  return (cat || "").replace(/_/g, " ");
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso.replace(/([+-]\d{2})(\d{2})$/, "$1:$2"));
  return isNaN(d) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function toast(msg, isError) {
  let t = $("toast");
  if (!t) {
    t = el("div", "toast hidden");
    t.id = "toast";
    t.setAttribute("role", "status");
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.className = "toast" + (isError ? " error" : "");
  clearTimeout(t._hide);
  t._hide = setTimeout(() => t.classList.add("hidden"), 6000);
}

/* ---------- record handoff: run page stores, report/script pages read ---------- */

function stashRecord(id, record) {
  try {
    sessionStorage.setItem("gl:lastRecord", JSON.stringify({ id, record }));
  } catch {
    /* storage full or blocked — /api/records covers it */
  }
}

async function fetchRecord(id) {
  try {
    const cached = JSON.parse(sessionStorage.getItem("gl:lastRecord") || "null");
    if (cached && cached.id === id) return cached.record;
  } catch {
    /* fall through to the API */
  }
  const res = await fetch(`/api/records/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error(`record ${id} not found`);
  return (await res.json()).record;
}

/* ---------- upload (offered from any page via the nav CTA) ---------- */

async function uploadScreenplay(file) {
  const form = new FormData();
  form.append("screenplay", file, file.name);
  try {
    const res = await fetch("/api/runs", { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    const { run_id } = await res.json();
    window.location.href = `/run?id=${run_id}`;
  } catch (e) {
    toast("upload failed: " + e.message, true);
  }
}

function promptUpload() {
  let input = $("gl-file-input");
  if (!input) {
    input = el("input");
    input.type = "file";
    input.accept = ".fountain,.txt,.pdf,text/plain,application/pdf";
    input.id = "gl-file-input";
    input.hidden = true;
    input.addEventListener("change", (e) => {
      if (e.target.files[0]) uploadScreenplay(e.target.files[0]);
    });
    document.body.appendChild(input);
  }
  input.click();
}

/* ---------- shared header / footer ---------- */

const NAV_LINKS = [
  ["/home", "Home"],
  ["/writer", "Writer's Room"],
  ["/cases", "Case studies"],
  ["/how-it-works", "How it works"],
  ["/faq", "FAQ"],
  ["/contact", "Contact"],
];

function injectChrome() {
  const path = window.location.pathname;

  const header = el("header", "site-header");
  const inner = el("div", "container header-inner");

  const brand = el("a", "brand");
  brand.href = "/home";
  brand.appendChild(el("span", "brand-dot"));
  brand.appendChild(el("span", "brand-name", "SCRIPTRISK"));
  inner.appendChild(brand);

  const nav = el("nav", "site-nav");
  nav.setAttribute("aria-label", "Main");
  for (const [href, label] of NAV_LINKS) {
    const a = el("a", href === path ? "active" : null, label);
    a.href = href;
    nav.appendChild(a);
  }
  inner.appendChild(nav);

  const actions = el("div", "header-actions");
  const replayBtn = el("a", "btn btn-secondary", "Watch a demo");
  replayBtn.href = "/run?replay=1";
  actions.appendChild(replayBtn);
  const cta = el("button", "btn btn-primary", "Analyze a screenplay");
  cta.type = "button";
  cta.addEventListener("click", promptUpload);
  actions.appendChild(cta);
  inner.appendChild(actions);

  header.appendChild(inner);
  document.body.prepend(header);

  const footer = el("footer", "site-footer");
  const finner = el("div", "container footer-inner");

  const col1 = el("div", "footer-col");
  const fbrand = el("div", "brand");
  fbrand.appendChild(el("span", "brand-dot"));
  fbrand.appendChild(el("span", "brand-name", "SCRIPTRISK"));
  col1.appendChild(fbrand);
  col1.appendChild(
    el(
      "p",
      "footer-blurb",
      "Screenplay clearance and production-risk analysis. Four AI desks, one cited report."
    )
  );
  finner.appendChild(col1);

  const mkCol = (title, links) => {
    const col = el("div", "footer-col");
    col.appendChild(el("h4", null, title));
    for (const [href, label, ext] of links) {
      const a = el("a", null, label);
      a.href = href;
      if (ext) {
        a.target = "_blank";
        a.rel = "noopener noreferrer";
      }
      col.appendChild(a);
    }
    return col;
  };
  finner.appendChild(
    mkCol("Product", [
      ["/how-it-works", "How it works"],
      ["/cases", "Case studies"],
      ["/writer", "Writer's Room"],
      ["/run?replay=1", "Watch a recorded analysis"],
      ["/faq", "FAQ"],
    ])
  );
  finner.appendChild(
    mkCol("Project", [
      ["https://github.com/lalitlouis/greenlight", "GitHub", true],
      ["/contact", "Contact the team"],
    ])
  );
  footer.appendChild(finner);

  const fine = el("div", "container footer-fine");
  fine.appendChild(
    el(
      "p",
      null,
      "Cost figures are rule-of-thumb estimates, not quotes. SCRIPTRISK is a research tool, " +
        "not legal advice. Built for the Agentic Cinema hackathon."
    )
  );
  fine.appendChild(el("p", null, "© 2026 SCRIPTRISK"));
  footer.appendChild(fine);
  document.body.appendChild(footer);
}

document.addEventListener("DOMContentLoaded", injectChrome);

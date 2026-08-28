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
  if (range[0] === 0 && range[1] === 0) return "no fee expected";
  const f = (n) => "$" + Math.round(n).toLocaleString("en-US");
  return `${f(range[0])}–${f(range[1])}`;
}

function safeUrl(url) {
  /* Citation and comp URLs originate from web results — render links only for
     http(s), never javascript: or anything else exotic. */
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
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
  const data = await res.json();
  if (data.kind === "running") {
    const err = new Error("This analysis is still running.");
    err.running = true;
    throw err;
  }
  return data.record;
}

/* ---------- upload with visible progress ---------- */

function showUploadOverlay(file) {
  let ov = $("upload-overlay");
  if (!ov) {
    ov = el("div", "upload-overlay");
    ov.id = "upload-overlay";
    const card = el("div", "upload-card");
    card.appendChild(el("h3", null, "Sending your screenplay"));
    card.appendChild(el("p", "up-file"));
    const bar = el("div", "up-bar");
    const fill = el("div", "up-fill");
    fill.id = "up-fill";
    bar.appendChild(fill);
    card.appendChild(bar);
    const status = el("p", "up-status");
    status.id = "up-status";
    card.appendChild(status);
    card.appendChild(
      el("p", "secure-note", "🔒 Encrypted in transit and at rest — never used to train models.")
    );
    ov.appendChild(card);
    document.body.appendChild(ov);
  }
  ov.querySelector(".up-file").textContent =
    `${file.name} · ${(file.size / 1024).toFixed(0)} KB`;
  ov.classList.remove("hidden");
  setUploadProgress(0, "Uploading — 0%");
  return ov;
}

function setUploadProgress(pct, statusText) {
  const fill = $("up-fill");
  const status = $("up-status");
  if (fill) fill.style.width = Math.min(100, pct) + "%";
  if (status) status.textContent = statusText;
}

function hideUploadOverlay() {
  $("upload-overlay")?.classList.add("hidden");
}

/* fetch() cannot report upload progress; XHR can. Resolves with parsed JSON. */
function uploadWithProgress(url, file, extraFields) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("screenplay", file, file.name);
    for (const [k, v] of Object.entries(extraFields || {})) {
      if (v) form.append(k, v);
    }
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((100 * e.loaded) / e.total);
        setUploadProgress(
          pct,
          pct < 100 ? `Uploading — ${pct}%` : "Upload complete — waking the desks…"
        );
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new Error("bad server response"));
        }
      } else {
        const err = new Error(xhr.responseText || `upload failed (${xhr.status})`);
        err.status = xhr.status;
        reject(err);
      }
    };
    xhr.onerror = () => reject(new Error("network error during upload"));
    xhr.send(form);
  });
}

/* Running an analysis requires an account. Returns true when it's fine to
   proceed; otherwise bounces through Google sign-in and back to this page.
   If the auth status hasn't loaded yet we let the server's 401 do the job. */
function requireSignIn() {
  if (window.__authConfigured && !window.__user) {
    toSignIn();
    return false;
  }
  return true;
}

function toSignIn() {
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.href = "/signin?next=" + next;
}

async function uploadScreenplay(file, sourceContext) {
  showUploadOverlay(file);
  try {
    const reviseOf = new URLSearchParams(window.location.search).get("revise") || "";
    const { run_id } = await uploadWithProgress("/api/runs", file, {
      source_context: sourceContext || "",
      previous_run_id: reviseOf,
    });
    setUploadProgress(100, "Desks are opening the script — taking you to the live run…");
    window.location.href = `/run?id=${run_id}`;
  } catch (e) {
    hideUploadOverlay();
    if (e.status === 401) {
      toSignIn();
      return;
    }
    toast("upload failed: " + e.message, true);
  }
}

/* Modern upload dialog: a dropzone modal with drag & drop, a styled browse
   button, and a confirm step — the native OS picker only appears on Browse. */
function openUploadModal(opts) {
  const { title, note, action, onFile } = opts;
  document.getElementById("upload-modal")?.remove();
  const overlay = el("div", "um-overlay");
  overlay.id = "upload-modal";
  const modal = el("div", "um-modal");
  const head = el("div", "um-head");
  head.appendChild(el("h3", null, title));
  const x = el("button", "um-close", "✕");
  x.type = "button";
  x.setAttribute("aria-label", "Close");
  head.appendChild(x);
  modal.appendChild(head);

  const zone = el("div", "um-zone");
  const zoneIdle = el("div", "um-zone-idle");
  zoneIdle.appendChild(el("span", "um-icon", "🎬"));
  zoneIdle.appendChild(el("p", "um-cta", "Drag your screenplay here"));
  zoneIdle.appendChild(el("p", "um-sub", note));
  const browse = el("button", "btn btn-secondary um-browse", "Browse files");
  browse.type = "button";
  zoneIdle.appendChild(browse);
  zone.appendChild(zoneIdle);
  const picked = el("div", "um-picked hidden");
  zone.appendChild(picked);
  modal.appendChild(zone);

  const ctxWrap = el("div", "um-context");
  const ctxLabel = el("label", "um-context-label", "Source material / life rights (optional)");
  const ctxInput = document.createElement("textarea");
  ctxInput.className = "um-context-input";
  ctxInput.maxLength = 2000;
  ctxInput.rows = 2;
  ctxInput.placeholder =
    'e.g. "Based on The Accidental Billionaires by Ben Mezrich; life rights: none" — helps the clearance desk separate adapted fact from invented scenes';
  ctxWrap.appendChild(ctxLabel);
  ctxWrap.appendChild(ctxInput);
  modal.appendChild(ctxWrap);

  const foot = el("div", "um-foot");
  const go = el("button", "btn btn-primary um-go", action);
  go.type = "button";
  go.disabled = true;
  foot.appendChild(el("p", "um-fine", "🔒 Encrypted in transit and at rest · never used to train models"));
  foot.appendChild(go);
  modal.appendChild(foot);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  const input = el("input");
  input.type = "file";
  input.accept = ".fountain,.txt,.pdf,text/plain,application/pdf";
  input.hidden = true;
  overlay.appendChild(input);

  let file = null;
  const setFile = (f) => {
    if (!f) return;
    const okTypes = /\.(fountain|txt|pdf)$/i;
    if (!okTypes.test(f.name)) {
      toast("Fountain, plain text, or PDF only.", true);
      return;
    }
    file = f;
    picked.textContent = "";
    picked.classList.remove("hidden");
    zoneIdle.classList.add("hidden");
    const card = el("div", "um-file");
    card.appendChild(el("span", "um-file-icon", f.name.toLowerCase().endsWith(".pdf") ? "📕" : "📄"));
    const meta = el("div", "um-file-meta");
    meta.appendChild(el("b", null, f.name));
    meta.appendChild(el("span", null, (f.size / 1024).toFixed(0) + " KB"));
    card.appendChild(meta);
    const swap = el("button", "cite-toggle", "Choose a different file");
    swap.type = "button";
    swap.addEventListener("click", () => input.click());
    card.appendChild(swap);
    picked.appendChild(card);
    go.disabled = false;
    go.focus();
  };

  browse.addEventListener("click", () => input.click());
  input.addEventListener("change", (e) => setFile(e.target.files[0]));
  ["dragover", "dragenter"].forEach((evt) =>
    zone.addEventListener(evt, (e) => {
      e.preventDefault();
      zone.classList.add("um-drag");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    zone.addEventListener(evt, (e) => {
      e.preventDefault();
      zone.classList.remove("um-drag");
    })
  );
  zone.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));
  const close = () => overlay.remove();
  x.addEventListener("click", close);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close();
  });
  document.addEventListener("keydown", function esc(e) {
    if (e.key === "Escape") {
      close();
      document.removeEventListener("keydown", esc);
    }
  });
  go.addEventListener("click", () => {
    if (!file) return;
    const context = ctxInput.value.trim();
    close();
    onFile(file, context);
  });
}

/* Styled confirm dialog — replaces window.confirm. Resolves true/false. */
function confirmDialog({ title, message, confirmLabel, danger }) {
  return new Promise((resolve) => {
    document.getElementById("confirm-modal")?.remove();
    const overlay = el("div", "um-overlay");
    overlay.id = "confirm-modal";
    const modal = el("div", "um-modal cd-modal");
    modal.appendChild(el("h3", "cd-title", title));
    modal.appendChild(el("p", "cd-msg", message));
    const row = el("div", "cd-row");
    const cancel = el("button", "btn btn-secondary", "Cancel");
    cancel.type = "button";
    const ok = el("button", "btn " + (danger ? "btn-danger-solid" : "btn-primary"), confirmLabel);
    ok.type = "button";
    row.appendChild(cancel);
    row.appendChild(ok);
    modal.appendChild(row);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    const done = (v) => {
      overlay.remove();
      resolve(v);
    };
    cancel.addEventListener("click", () => done(false));
    ok.addEventListener("click", () => done(true));
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) done(false);
    });
    document.addEventListener("keydown", function esc(e) {
      if (e.key === "Escape") {
        done(false);
        document.removeEventListener("keydown", esc);
      }
    });
    cancel.focus();
  });
}

function promptUpload() {
  if (!requireSignIn()) return;
  openUploadModal({
    title: "Analyze a screenplay",
    note: "Fountain, PDF, or Final Draft (.fdx) · up to 5 MB · 10–35 min of real investigation",
    action: "Start the analysis",
    onFile: uploadScreenplay,
  });
}

function brandName() {
  const n = el("span", "brand-name");
  n.appendChild(el("span", "brand-script", "SCRIPT"));
  n.appendChild(el("span", "brand-risk", "RISK"));
  return n;
}

/* ---------- shared header / footer ---------- */

const NAV_LINKS = [
  ["/home", "Home"],
  ["/writer", "Writer's Room"],
  ["/cases", "Case studies"],
  ["/how-it-works", "How it works"],
  ["/desks", "The desks"],
  ["/faq", "FAQ"],
  ["/contact", "Contact"],
];

function injectChrome() {
  // The one-sheet is a standalone artifact page — no site chrome around the poster.
  if (document.body.classList.contains("os-body") || document.body.classList.contains("bd-body")) return;
  const path = window.location.pathname;

  const header = el("header", "site-header");
  const inner = el("div", "container header-inner");

  const brand = el("a", "brand");
  brand.href = "/home";
  brand.appendChild(el("span", "brand-dot"));
  brand.appendChild(brandName());
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
  const theme = el("button", "theme-toggle");
  theme.type = "button";
  const applyThemeIcon = () => {
    const light = document.documentElement.dataset.theme === "light";
    theme.textContent = light ? "☾" : "☀";
    theme.setAttribute("aria-label", light ? "Switch to dark mode" : "Switch to light mode");
    theme.title = theme.getAttribute("aria-label");
  };
  applyThemeIcon();
  theme.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "light" ? "" : "light";
    if (next) document.documentElement.dataset.theme = next;
    else delete document.documentElement.dataset.theme;
    try {
      if (next) localStorage.setItem("sr-theme", next);
      else localStorage.removeItem("sr-theme");
    } catch (e) {
      /* private mode: theme just won't persist */
    }
    applyThemeIcon();
  });
  actions.appendChild(theme);
  const cta = el("button", "btn btn-primary", "Analyze a screenplay");
  cta.type = "button";
  cta.addEventListener("click", promptUpload);
  actions.appendChild(cta);
  const authSlot = el("span", "auth-slot");
  authSlot.id = "auth-slot";
  actions.appendChild(authSlot);
  inner.appendChild(actions);

  header.appendChild(inner);
  document.body.prepend(header);

  const footer = el("footer", "site-footer");
  const finner = el("div", "container footer-inner");

  const col1 = el("div", "footer-col");
  const fbrand = el("div", "brand");
  fbrand.appendChild(el("span", "brand-dot"));
  fbrand.appendChild(brandName());
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
      ["/compare", "Compare tools"],
      ["/writer", "Writer's Room"],
      ["/run?replay=1", "Watch a recorded analysis"],
      ["/faq", "FAQ"],
    ])
  );
  finner.appendChild(
    mkCol("Project", [
      ["https://github.com/lalitlouis/greenlight", "GitHub", true],
      ["/contact", "Contact the team"],
      ["/terms", "Terms of service"],
      ["/privacy", "Privacy policy"],
      ["/security", "Security"],
      ["/methodology", "Methodology"],
    ])
  );
  footer.appendChild(finner);

  const fine = el("div", "container footer-fine");
  fine.appendChild(
    el(
      "p",
      null,
      "Screenplays are encrypted in transit and at rest and never used to train AI models. " +
        "Cost figures are rule-of-thumb estimates, not quotes. ScriptRisk is a research tool, " +
        "not legal advice. Built for the Agentic Cinema hackathon."
    )
  );
  fine.appendChild(el("p", null, "© 2026 SCRIPTRISK"));
  footer.appendChild(fine);
  document.body.appendChild(footer);
  hydrateAuth(); // must run AFTER the chrome is in the DOM — the slot is found by id
}

async function hydrateAuth() {
  const slot = $("auth-slot");
  if (!slot) return;
  try {
    const { configured, user, is_admin } = await (await fetch("/api/auth/status")).json();
    window.__isAdmin = is_admin;
    window.__authConfigured = configured;
    window.__user = user || null;
    slot.textContent = "";
    if (!configured) return; // sign-in simply isn't offered until it exists
    if (!user) {
      const a = el("a", "btn btn-secondary", "Sign in");
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      a.href = "/signin?next=" + next;
      slot.appendChild(a);
      return;
    }
    const wrap = el("div", "auth-menu-wrap");
    const trigger = el("button", "auth-trigger");
    trigger.type = "button";
    trigger.setAttribute("aria-haspopup", "menu");
    trigger.setAttribute("aria-expanded", "false");
    trigger.title = user.email;
    if (user.picture) {
      const img = el("img", "auth-pic");
      img.src = user.picture;
      img.alt = "Account";
      img.referrerPolicy = "no-referrer";
      trigger.appendChild(img);
    } else {
      trigger.appendChild(el("span", "auth-pic auth-pic-fallback", (user.name || user.email || "?")[0].toUpperCase()));
    }
    trigger.appendChild(el("span", "auth-caret", "▾"));
    wrap.appendChild(trigger);

    const menu = el("div", "auth-menu hidden");
    menu.setAttribute("role", "menu");
    const who = el("div", "auth-menu-who");
    who.appendChild(el("b", null, user.name || "Signed in"));
    who.appendChild(el("span", null, user.email || ""));
    menu.appendChild(who);
    const mkItem = (label, href) => {
      const it = el("a", "auth-menu-item", label);
      it.href = href;
      it.setAttribute("role", "menuitem");
      menu.appendChild(it);
      return it;
    };
    mkItem("My reports", "/my");
    if (window.__isAdmin) mkItem("Admin", "/admin");
    const out = el("button", "auth-menu-item auth-menu-out", "Sign out");
    out.type = "button";
    out.setAttribute("role", "menuitem");
    out.addEventListener("click", async () => {
      await fetch("/auth/logout", { method: "POST" });
      window.location.href = "/home";
    });
    menu.appendChild(out);
    wrap.appendChild(menu);

    const close = () => {
      menu.classList.add("hidden");
      trigger.setAttribute("aria-expanded", "false");
    };
    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const opening = menu.classList.contains("hidden");
      menu.classList.toggle("hidden");
      trigger.setAttribute("aria-expanded", opening ? "true" : "false");
    });
    document.addEventListener("click", (e) => {
      if (!wrap.contains(e.target)) close();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close();
    });
    slot.appendChild(wrap);
  } catch {
    /* nav works without auth */
  }
}

function beacon(level, event, detail) {
  try {
    fetch("/api/client-log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        level,
        event,
        detail: String(detail || "").slice(0, 300),
        page: window.location.pathname + window.location.search,
      }),
      keepalive: true,
    });
  } catch {
    /* telemetry must never break the page */
  }
}

window.addEventListener("error", (e) => {
  beacon("error", "js_error", (e.message || "") + " @ " + (e.filename || "") + ":" + (e.lineno || ""));
  /* A silent JS error looks like a frozen page. Make it a report instead. */
  try {
    toast("Page error: " + (e.message || "unknown") + " — try a hard refresh (Cmd+Shift+R).", true);
  } catch {
    /* toast itself failed; nothing more to do */
  }
});

document.addEventListener("DOMContentLoaded", injectChrome);

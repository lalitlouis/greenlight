/* Report page: renders one record — score, rating prediction, findings (cited),
   rejections, open questions, adjudication. The render-layer invariant: a flag
   without citations does not render. */

"use strict";

let RUN_ID = null;
let IS_CASE = false;

function gotoScene(sid) {
  window.location.href = `/script?run=${encodeURIComponent(RUN_ID)}#scene-${sid}`;
}

function citationCard(c, idx, total) {
  const wrap = el("div");
  wrap.appendChild(el("div", "blk-label", `Citation ${idx + 1} of ${total}`));
  const card = el("div", "cite");
  card.appendChild(el("q", null, c.excerpt || ""));
  const src = el("div", "src");
  src.appendChild(
    el("span", "via", (c.via || c.source_type || "source").replace("_", " "))
  );
  const citeUrl = safeUrl(c.url);
  if (citeUrl) {
    const a = el("a", null, citeUrl.replace(/^https?:\/\//, "").slice(0, 60));
    a.href = citeUrl;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    src.appendChild(a);
  }
  if (c.title) src.appendChild(el("span", null, "· " + c.title));
  card.appendChild(src);
  wrap.appendChild(card);
  return wrap;
}

/* Word-level diff: LCS over words so the before/after highlights exactly what
   changed. Patches are short (scene lines), so O(n*m) is nothing. */
function wordDiff(a, b) {
  const A = a.split(/(\s+)/), B = b.split(/(\s+)/);
  const n = A.length, m = B.length;
  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const out = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) { out.push({ t: "same", w: A[i] }); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push({ t: "del", w: A[i] }); i++; }
    else { out.push({ t: "add", w: B[j] }); j++; }
  }
  while (i < n) out.push({ t: "del", w: A[i++] });
  while (j < m) out.push({ t: "add", w: B[j++] });
  return out;
}

function diffBox(label, diff, keep) {
  const box = el("div", "diff-box " + (keep === "del" ? "diff-before" : "diff-after"));
  box.appendChild(el("span", "diff-label", label));
  const pre = el("pre", "diff-text");
  for (const part of diff) {
    if (part.t === "same") pre.appendChild(document.createTextNode(part.w));
    else if (part.t === keep) pre.appendChild(el("mark", "d-" + keep, part.w));
  }
  box.appendChild(pre);
  return box;
}

/* Accepted patches accumulate here; the floating bar exports them. */
const ACCEPTED = new Map(); // key -> patch

function patchKey(patch) {
  return patch.scene_id + "|" + patch.find.slice(0, 60);
}

function refreshExportBar() {
  let bar = $("export-bar");
  if (!ACCEPTED.size) {
    bar?.remove();
    return;
  }
  if (!bar) {
    bar = el("div", "export-bar");
    bar.id = "export-bar";
    const label = el("span", "eb-label");
    label.id = "eb-label";
    bar.appendChild(label);
    const dlF = el("button", "btn btn-primary eb-btn", "Download .fountain");
    dlF.type = "button";
    dlF.addEventListener("click", () => downloadRevised("fountain"));
    const dlX = el("button", "btn btn-secondary eb-btn", "Download .fdx (beta)");
    dlX.type = "button";
    dlX.addEventListener("click", () => downloadRevised("fdx"));
    bar.appendChild(dlF);
    bar.appendChild(dlX);
    document.body.appendChild(bar);
    if (window.FX?.on) gsap.fromTo(bar, { y: 60, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4, ease: "power3.out" });
  }
  $("eb-label").textContent =
    ACCEPTED.size + (ACCEPTED.size === 1 ? " fix accepted" : " fixes accepted") + " — revised script with revision marks:";
}

async function downloadRevised(format) {
  try {
    const res = await fetch("/api/revise", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: RUN_ID, format, patches: [...ACCEPTED.values()] }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const blob = await res.blob();
    const skipped = Number(res.headers.get("X-Patches-Skipped") || 0);
    const cd = res.headers.get("Content-Disposition") || "";
    const name = (cd.match(/filename="([^"]+)"/) || [])[1] || "revised." + format;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
    if (skipped) toast(skipped + " patch(es) no longer applied cleanly and were skipped.", true);
  } catch (e) {
    toast("Export failed: " + e.message.slice(0, 140), true);
  }
}

function renderFix(container, fix) {
  container.textContent = "";
  container.appendChild(el("p", "fix-summary", fix.summary || ""));
  for (const patch of fix.patches || []) {
    const card = el("div", "fix-patch");
    const head = el("div", "fix-patch-head");
    head.appendChild(el("span", "scene-link inert", patch.scene_id));
    head.appendChild(el("span", "fix-rationale", patch.rationale || ""));
    card.appendChild(head);
    const diff = wordDiff(patch.find, patch.replace);
    const cols = el("div", "fix-cols");
    cols.appendChild(diffBox("As written", diff, "del"));
    cols.appendChild(diffBox("Proposed rewrite", diff, "add"));
    card.appendChild(cols);
    const controls = el("div", "fix-controls");
    const accept = el("button", "btn btn-secondary accept-btn", "Accept this fix");
    accept.type = "button";
    const key = patchKey(patch);
    accept.addEventListener("click", () => {
      if (ACCEPTED.has(key)) {
        ACCEPTED.delete(key);
        accept.textContent = "Accept this fix";
        accept.classList.remove("accepted");
      } else {
        ACCEPTED.set(key, { scene_id: patch.scene_id, find: patch.find, replace: patch.replace });
        accept.textContent = "✓ Accepted — in the revised script";
        accept.classList.add("accepted");
      }
      refreshExportBar();
    });
    controls.appendChild(accept);
    const copy = el("button", "cite-toggle", "Copy the new text");
    copy.type = "button";
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(patch.replace);
        copy.textContent = "Copied ✓";
        setTimeout(() => { copy.textContent = "Copy the new text"; }, 2000);
      } catch { toast("Copy failed — select the text manually.", true); }
    });
    controls.appendChild(copy);
    card.appendChild(controls);
    container.appendChild(card);
  }
}

function fixControls(f) {
  const wrap = el("div", "fix-wrap");
  const row = el("div", "fix-row");
  const btn = el("button", "btn btn-secondary fix-btn", "Propose a fix");
  btn.type = "button";
  row.appendChild(btn);
  row.appendChild(el("span", "fix-beta", "Free during beta · $39/script after"));
  wrap.appendChild(row);
  const result = el("div", "fix-result");
  wrap.appendChild(result);
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Drafting a fix — ~20s…";
    try {
      const res = await fetch("/api/fix", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: RUN_ID, flag_id: f.flag_id }),
      });
      if (!res.ok) throw new Error(await res.text());
      renderFix(result, await res.json());
      btn.textContent = "Draft another fix";
    } catch (e) {
      toast("Fix failed: " + e.message.slice(0, 160), true);
      btn.textContent = "Propose a fix";
    } finally {
      btn.disabled = false;
    }
  });
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
    rej.appendChild(el("b", null, "Rejected in verification — "));
    rej.appendChild(document.createTextNode(f.rejection_reason));
    ex.appendChild(rej);
  }
  return ex;
}

function flagRow(f, opts) {
  const { rejected = false, expanded = false } = opts || {};
  const row = el("article", "card flag" + (rejected ? " rejected" : ""));
  row.id = "flag-" + f.flag_id;
  row.appendChild(el("span", "sev-bar bar-" + f.severity));

  const scenes = el("div", "scenes");
  scenes.appendChild(el("span", null, f.flag_id));
  for (const sid of f.scene_ids || []) {
    if (IS_CASE) {
      scenes.appendChild(el("span", "scene-link inert", sid));
      continue;
    }
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
  top.appendChild(el("span", "cat", prettyCat(f.category)));
  top.appendChild(el("span", "by by-" + f.agent, prettyCat(f.agent)));
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
  const action = f.remedy?.action;
  if (!IS_CASE && !rejected && action && action !== "NO_ACTION") {
    main.appendChild(fixControls(f));
  }
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

function renderPrediction(root, pred) {
  if (!pred || !(pred.comparables || []).length) return;
  const sec = el("div", "section-head");
  sec.id = "sec-rating";
  sec.appendChild(el("h2", null, "Rating prediction"));
  sec.appendChild(el("p", "lede", "Evidence, not opinion — your nearest comparables from 2,487 released films (corpus updated Aug 2026)."));
  root.appendChild(sec);

  const card = el("div", "card pred-card");
  const head = el("div", "pred-head");
  const ratings = el("div", "pred-ratings");
  const predBox = el("div", "pred-box");
  predBox.appendChild(el("span", "pred-label", "Predicted, as written"));
  predBox.appendChild(el("b", "rating-badge r-" + pred.predicted, pred.predicted));
  ratings.appendChild(predBox);
  if (pred.target && pred.target !== pred.predicted) {
    ratings.appendChild(el("span", "pred-vs", "vs"));
    const tgtBox = el("div", "pred-box");
    tgtBox.appendChild(el("span", "pred-label", "Production target"));
    tgtBox.appendChild(el("b", "rating-badge target", pred.target));
    ratings.appendChild(tgtBox);
  }
  head.appendChild(ratings);

  const meta = el("div", "pred-meta");
  if (pred.rationale) meta.appendChild(el("p", "pred-rationale", pred.rationale));
  const comps = pred.comparables || [];
  const tallies = {};
  for (const c of comps) tallies[c.rating] = (tallies[c.rating] || 0) + 1;
  const majority = Object.entries(tallies).sort((a, b) => b[1] - a[1])[0];
  const same = tallies[pred.predicted] || 0;
  let line = `${same} of your ${comps.length} nearest released comparables are rated ${pred.predicted}.`;
  if (majority && majority[0] !== pred.predicted && majority[1] > same) {
    line += ` The plurality — ${majority[1]} of ${comps.length} — are rated ${majority[0]}; treat the prediction with caution.`;
  }
  meta.appendChild(el("p", "pred-evidence", line));
  head.appendChild(meta);
  card.appendChild(head);

  const list = el("div", "comps");
  const maxD = Math.max(...comps.map((c) => c.distance || 0), 0.001);
  for (const c of comps) {
    const row = el("div", "comp-row");
    row.appendChild(el("b", "comp-rating r-" + c.rating, c.rating));
    const main = el("div", "comp-main");
    main.appendChild(el("span", "comp-title", `${c.title}${c.year ? " (" + c.year + ")" : ""}`));
    if (c.rationale) main.appendChild(el("span", "comp-quote", c.rationale));
    const compUrl = safeUrl(c.source_url);
    if (compUrl) {
      const a = el("a", "comp-src", "source");
      a.href = compUrl;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      main.appendChild(a);
    }
    row.appendChild(main);
    const sim = el("div", "comp-sim");
    const bar = el("div", "comp-bar");
    const fill = el("div", "comp-fill");
    fill.dataset.grow = String(Math.round(100 * (1 - c.distance / (maxD * 1.15))));
    if (!window.FX?.on) fill.style.width = fill.dataset.grow + "%";
    bar.appendChild(fill);
    sim.appendChild(bar);
    sim.appendChild(el("span", "comp-d", "d " + (c.distance ?? 0).toFixed(3)));
    row.appendChild(sim);
    list.appendChild(row);
  }
  card.appendChild(list);

  if ((pred.beats_to_cut || []).length) {
    const cuts = el("div", "cuts");
    cuts.appendChild(el("div", "blk-label", `The cut list toward ${pred.target || "your target"} — test each cut`));
    cuts.appendChild(
      el("p", "cuts-hint", "Check cuts to re-run the comparables search on your revised content profile — live against all 2,487 films. Cuts are levers, not guarantees: the simulator measures how far each one actually moves the rating.")
    );
    const ol = el("ol", "cuts-list");
    pred.beats_to_cut.forEach((b, i) => {
      const li = el("li");
      const lab = el("label", "cut-item");
      const cb = el("input");
      cb.type = "checkbox";
      cb.dataset.beat = String(i);
      lab.appendChild(cb);
      lab.appendChild(el("span", null, b));
      li.appendChild(lab);
      ol.appendChild(li);
    });
    cuts.appendChild(ol);
    const out = el("div", "whatif-out hidden");
    out.id = "whatif-out";
    cuts.appendChild(out);
    card.appendChild(cuts);
    initWhatIf(cuts, pred);
  }
  root.appendChild(card);
}

/* ---------- what-if: re-run the evidence with cuts applied ---------- */
let _whatifSeq = 0;

function initWhatIf(cutsRoot, pred) {
  const out = cutsRoot.querySelector("#whatif-out");
  const baseTarget = (pred.comparables || []).filter((c) => c.rating === pred.target).length;
  const total = (pred.comparables || []).length || 8;
  let timer = null;

  const run = async () => {
    const live = [...cutsRoot.querySelectorAll("input[type=checkbox]")];
    const cuts = live.filter((b) => b.checked && b.dataset.beat != null).map((b) => Number(b.dataset.beat));
    const extra = live.filter((b) => b.checked && b.dataset.extra).map((b) => b.dataset.extra);
    const seq = ++_whatifSeq;
    if (!cuts.length && !extra.length) {
      out.classList.add("hidden");
      setProjectedBadge(null);
      return;
    }
    out.classList.remove("hidden");
    out.textContent = "";
    const loadWrap = el("div", "wi-loadwrap");
    const stage = el("p", "wi-loading", "Rewriting the content profile without those beats…");
    const bar = el("div", "wi-bar");
    const fill = el("div", "wi-fill");
    bar.appendChild(fill);
    loadWrap.appendChild(stage);
    loadWrap.appendChild(bar);
    out.appendChild(loadWrap);
    const t0 = Date.now();
    const tick = setInterval(() => {
      const s = (Date.now() - t0) / 1000;
      // paced against the typical ~8s round trip; holds at 92% until the result lands
      fill.style.width = Math.min(92, s * 12) + "%";
      if (s > 3) stage.textContent = "Searching 2,487 released films for the new nearest comparables…";
      if (s > 8) stage.textContent = "Almost there — ranking comparables…";
    }, 200);
    try {
      const res = await fetch("/api/whatif", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: RUN_ID, cuts, extra }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      const d = await res.json();
      if (seq !== _whatifSeq) return; // a newer toggle superseded this one
      clearInterval(tick);
      renderWhatIf(out, d, pred, baseTarget, total, cuts.length + extra.length);
      maybeOfferSuggestions(out, cutsRoot, pred, d, cuts, extra);
      setProjectedBadge(d.projected);
    } catch (e) {
      clearInterval(tick);
      if (seq !== _whatifSeq) return;
      out.textContent = "";
      out.appendChild(el("p", "wi-err", "Could not project: " + e.message));
    }
  };

  cutsRoot.addEventListener("change", (e) => {
    if (e.target.matches?.("input[type=checkbox]")) {
      clearTimeout(timer);
      timer = setTimeout(run, 450);
    }
  });
}

/* When the cuts don't reach the target, the simulator offers to find more
   levers — each suggestion lands as a new checkbox, testable like any cut. */
function maybeOfferSuggestions(out, cutsRoot, pred, d, cuts, extra) {
  if (d.projected === pred.target) return;
  const wrap = el("div", "wi-suggest");
  const btn = el("button", "btn btn-secondary wi-suggest-btn", `What else would move it to ${pred.target}?`);
  btn.type = "button";
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Analyzing what still patterns " + d.projected + "…";
    try {
      const res = await fetch("/api/whatif/suggest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: RUN_ID, cuts, extra }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      const s = await res.json();
      const fresh = (s.suggestions || []).filter(
        (txt) => ![...cutsRoot.querySelectorAll(".cut-item span")].some((n) => n.textContent === txt)
      );
      if (!fresh.length) {
        btn.textContent = "No further content levers found — what remains is structural.";
        return;
      }
      const ol = cutsRoot.querySelector(".cuts-list");
      for (const txt of fresh) {
        const li = el("li");
        const lab = el("label", "cut-item cut-suggested");
        const cb = el("input");
        cb.type = "checkbox";
        cb.dataset.extra = txt;
        lab.appendChild(cb);
        lab.appendChild(el("span", null, txt));
        lab.appendChild(el("i", "cut-tag", "simulator suggestion"));
        li.appendChild(lab);
        ol.appendChild(li);
        if (window.FX?.on) gsap.fromTo(li, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.4 });
      }
      wrap.replaceChildren(
        el("p", "cuts-hint", `${fresh.length} suggestion${fresh.length === 1 ? "" : "s"} added to the cut list above — check them to test, same evidence pipeline.`)
      );
    } catch (e) {
      btn.disabled = false;
      btn.textContent = "What else would move it to " + pred.target + "?";
      toast("Suggestion failed: " + e.message.slice(0, 140), true);
    }
  });
  wrap.appendChild(btn);
  out.appendChild(wrap);
}

function setProjectedBadge(rating) {
  document.getElementById("wi-projected-box")?.remove();
  if (!rating) return;
  const ratings = document.querySelector(".pred-ratings");
  if (!ratings) return;
  const box = el("div", "pred-box wi-proj");
  box.id = "wi-projected-box";
  box.appendChild(el("span", "pred-label", "Projected with cuts"));
  box.appendChild(el("b", "rating-badge wi-badge r-" + rating, rating));
  ratings.appendChild(box);
  if (window.FX?.on) gsap.fromTo(box, { scale: 0.7, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.4, ease: "back.out(1.6)" });
}

function renderWhatIf(out, d, pred, baseTarget, total, nCuts) {
  out.textContent = "";
  const newTarget = d.tally?.[pred.target] || 0;
  const head = el("div", "wi-head");
  head.appendChild(el("b", "rating-badge sm r-" + d.projected, d.projected));
  const moved = newTarget - baseTarget;
  let verdict;
  if (d.projected === pred.target) {
    verdict = `These ${nCuts} cut${nCuts === 1 ? "" : "s"} flip the projection: ${newTarget} of ${total} nearest comparables now rate ${pred.target}.`;
  } else if (moved > 0) {
    verdict = `Closer, not clear: ${pred.target} comparables move ${baseTarget} → ${newTarget} of ${total}. What remains in the profile still patterns with ${d.projected} films.`;
  } else {
    verdict = `No movement — ${d.tally?.[d.projected] || 0} of ${total} nearest comparables still rate ${d.projected}. These beats weren't what was driving it.`;
  }
  head.appendChild(el("p", "wi-verdict", verdict));
  out.appendChild(head);
  if (d.revised_rationale) out.appendChild(el("p", "wi-rationale", "Revised profile: “" + d.revised_rationale + "”"));
  if (d.projected !== pred.target) {
    out.appendChild(
      el("p", "wi-note", "The rating hinges on the whole content profile, not only the flagged beats — the simulator re-runs the real comparables search, so it will disagree with the cut list when the remaining content still patterns higher. That honesty is the product.")
    );
  }
  const row = el("div", "wi-comps");
  for (const c of (d.comparables || []).slice(0, 5)) {
    const chipEl = el("span", "wi-comp r-line-" + c.rating);
    chipEl.appendChild(el("b", "wi-r r-" + c.rating, c.rating));
    chipEl.appendChild(document.createTextNode(`${c.title}${c.year ? " (" + c.year + ")" : ""}`));
    row.appendChild(chipEl);
  }
  out.appendChild(row);
}

/* Sticky "on this page" navigator: the whole report visible from the top.
   Built from what this record actually contains — no dead links. */
function buildReportNav(record, rep) {
  const cited = (record.flags || []).filter((f) => (f.citations || []).length > 0);
  const oqCount = Object.values(record.open_questions || {}).flat().length;
  const entries = [
    rep.est_clearance_cost_usd ? ["sec-cost", "Cost exposure", null] : null,
    rep.rating_prediction?.predicted ? ["sec-rating", "Rating + simulator", null] : null,
    ["sec-findings", "Findings", cited.length],
    (record.rejected_flags || []).length ? ["sec-rejected", "Rejected", record.rejected_flags.length] : null,
    oqCount ? ["sec-questions", "Open questions", oqCount] : null,
    (record.adjudication_notes || []).length ? ["sec-adjudication", "Adjudication", null] : null,
  ].filter(Boolean);

  const nav = el("nav", "report-nav");
  nav.setAttribute("aria-label", "Report sections");
  nav.appendChild(el("span", "rn-label", "In this report"));
  const chips = [];
  for (const [id, label, count] of entries) {
    const a = el("a", "rn-chip");
    a.href = "#" + id;
    a.appendChild(document.createTextNode(label));
    if (count != null) a.appendChild(el("b", null, String(count)));
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const node = $(id);
      if (!node) return;
      node.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", "#" + id);
    });
    chips.push([a, id]);
    nav.appendChild(a);
  }
  // active highlight follows the scroll
  let raf = 0;
  window.addEventListener("scroll", () => {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      let current = null;
      for (const [, id] of chips) {
        const node = $(id);
        if (node && node.getBoundingClientRect().top < 140) current = id;
      }
      for (const [a, id] of chips) a.classList.toggle("active", id === current);
    });
  }, { passive: true });
  return nav;
}

function renderReport(record) {
  const root = $("report");
  root.textContent = "";
  const rep = record.report || {};
  const counts = rep.counts || {};
  const score = rep.greenlight_score ?? "—";
  const blockers = counts.BLOCKER || 0;
  const tone = blockers > 0 || score < 40 ? "bad" : score < 75 ? "mid" : "good";

  $("rpt-title").textContent = record.script_title || "Report";

  IS_CASE = record.kind === "case_study";
  if (record.kind === "case_study" && record.case) {
    $("script-link")?.classList.add("hidden"); // the screenplay text is not reproduced
    const strip = el("div", "case-strip");
    const head = el("p", "case-hook");
    head.appendChild(el("b", null, `${record.case.title} (${record.case.year}) — case study. `));
    head.appendChild(document.createTextNode(record.case.hook || ""));
    strip.appendChild(head);
    strip.appendChild(el("p", "case-note", record.case.note || ""));
    root.appendChild(strip);
  }

  const head = el("div", "card rpt-head");
  const scoreBox = el("div", "score " + tone);
  if (typeof score === "number" && !window.FX?.on) {
    scoreBox.style.setProperty("--scorepct", String(score));
  }
  scoreBox.appendChild(el("b", null, String(score)));
  scoreBox.appendChild(el("span", "of", "/100"));
  head.appendChild(scoreBox);

  const meta = el("div", "score-meta");
  const verdict =
    blockers > 0
      ? `Not cleared — ${blockers} blocker${blockers === 1 ? "" : "s"}`
      : tone === "good"
        ? "Cleared, with conditions"
        : "Conditional — remedies required";
  meta.appendChild(el("span", "verdict " + tone, verdict));
  meta.appendChild(
    el(
      "p",
      "score-caveat",
      "Scores are directional — independent re-runs typically land within a few points. " +
        "The cited findings below are the product; the number is a summary of them."
    )
  );
  const proj = el("span", "proj");
  proj.appendChild(
    document.createTextNode(
      `${(record.flags || []).length} findings · ` +
        `${(record.rejected_flags || []).length} rejected in verification · ` +
        `${(record.entities || []).length} entities researched`
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
  meta.appendChild(el("span", "est-note", "Cost figures are estimates, not quotes."));
  head.appendChild(meta);

  const dims = rep.dimension_scores;
  if (dims) {
    const dimRow = el("div", "dims");
    const names = {
      clearance_counsel: "Rights",
      ratings_board: "Ratings",
      safety_underwriter: "Safety",
      territory_censor: "Territory",
    };
    for (const [desk, label] of Object.entries(names)) {
      const v = dims[desk];
      if (v == null) continue;
      const cell = el("div", "dim by-" + desk);
      cell.appendChild(el("b", null, String(v)));
      cell.appendChild(el("span", null, label));
      dimRow.appendChild(cell);
    }
    dimRow.appendChild(
      el("span", "dims-note", "Per-desk scores; the composite compounds all desks' findings.")
    );
    meta.appendChild(dimRow);
  }

  const tally = el("div", "tally");
  for (const sev of SEVS) {
    const cell = el("div");
    cell.appendChild(el("b", "sev-" + sev, String(counts[sev] || 0)));
    cell.appendChild(el("span", null, sev));
    if (counts[sev]) {
      cell.classList.add("tally-link");
      cell.title = "Jump to the first " + sev + " finding";
      cell.addEventListener("click", () => {
        const target = (record.flags || []).find((f) => f.severity === sev);
        const node = target && $("flag-" + target.flag_id);
        if (!node) return;
        node.querySelector(".expand")?.classList.remove("hidden");
        node.scrollIntoView({ behavior: "smooth", block: "center" });
        node.classList.add("hilite");
        setTimeout(() => node.classList.remove("hilite"), 2200);
      });
    }
    tally.appendChild(cell);
  }
  head.appendChild(tally);
  root.appendChild(head);
  root.appendChild(buildReportNav(record, rep));

  const drivers = (record.flags || [])
    .filter((f) => f.remedy?.est_cost_usd)
    .sort((a, b) => b.remedy.est_cost_usd[1] - a.remedy.est_cost_usd[1])
    .slice(0, 3);
  if (drivers.length && rep.est_clearance_cost_usd) {
    const card = el("div", "card drivers-card");
    card.id = "sec-cost";
    const h = el("div", "drivers-head");
    h.appendChild(el("h3", null, "Estimated clearance exposure"));
    h.appendChild(el("b", "drivers-total", money(rep.est_clearance_cost_usd)));
    card.appendChild(h);
    const ul = el("div", "drivers");
    drivers.forEach((f, i) => {
      const row = el("button", "driver");
      row.type = "button";
      row.addEventListener("click", () => {
        const node = $("flag-" + f.flag_id);
        node?.querySelector(".expand")?.classList.remove("hidden");
        node?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
      row.appendChild(el("span", "driver-rank", String(i + 1)));
      row.appendChild(el("span", "driver-name", prettyCat(f.category)));
      row.appendChild(el("b", null, money(f.remedy.est_cost_usd)));
      ul.appendChild(row);
    });
    card.appendChild(ul);
    card.appendChild(
      el("p", "est-note", "The number for a financing conversation: total exposure, ranked by driver. Estimates, not quotes.")
    );
    root.appendChild(card);
  }

  renderPrediction(root, rep.rating_prediction);

  const cited = (record.flags || []).filter((f) => (f.citations || []).length > 0);
  const secFlags = el("div", "section-head");
  secFlags.id = "sec-findings";
  secFlags.appendChild(el("h2", null, `Findings — ${cited.length}, every one cited`));
  root.appendChild(secFlags);
  const flags = el("div", "flags");
  cited.forEach((f) => flags.appendChild(flagRow(f, { expanded: f.severity === "BLOCKER" })));
  root.appendChild(flags);

  const rejectedFlags = record.rejected_flags || [];
  if (rejectedFlags.length) {
    const sec = el("div", "section-head");
    sec.id = "sec-rejected";
    sec.appendChild(el("h2", null, `Rejected in verification — ${rejectedFlags.length}`));
    const rate = Math.round(
      (100 * rejectedFlags.length) / Math.max(1, rejectedFlags.length + (record.flags || []).length)
    );
    sec.appendChild(
      el(
        "p",
        "lede",
        `An independent verifier read every citation and rejected ${rate}% of draft findings ` +
          "in this analysis. These claims did not survive."
      )
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
    sec.id = "sec-questions";
    sec.appendChild(el("h2", null, `Open questions — ${oqItems.length} honest unknowns`));
    root.appendChild(sec);
    const ul = el("ul", "plain-list");
    for (const [desk, q] of oqItems) {
      const li = el("li");
      li.appendChild(el("span", "who", prettyCat(desk)));
      li.appendChild(document.createTextNode(q));
      ul.appendChild(li);
    }
    root.appendChild(ul);
  }

  const notes = record.adjudication_notes || [];
  if (notes.length) {
    const sec = el("div", "section-head");
    sec.id = "sec-adjudication";
    sec.appendChild(el("h2", null, "Adjudication — merges and conflict resolutions"));
    root.appendChild(sec);
    const ul = el("ul", "plain-list");
    for (const n of notes) ul.appendChild(el("li", null, n));
    root.appendChild(ul);
  }

  if (window.FX?.on) {
    FX.scoreRing(scoreBox, typeof score === "number" ? score : 0);
    FX.growBars(root);
    FX.staggerIn(root.querySelectorAll(".flag"));
  }

  // Anonymous and owned live runs (hex ids) can be deleted from here; curated
  // demo records (run_*/case_* stems) cannot — the server refuses those anyway.
  if (!IS_CASE && /^w?[0-9a-f]{11,12}$/.test(RUN_ID)) {
    const zone = el("div", "card delete-zone");
    zone.appendChild(
      el("p", null, "Done with this analysis? Deleting removes the script, the report, and the run record from our storage.")
    );
    const btn = el("button", "btn btn-danger", "Delete this analysis");
    btn.type = "button";
    btn.addEventListener("click", async () => {
      if (!window.confirm("Permanently delete this analysis and its uploaded script?")) return;
      btn.disabled = true;
      btn.textContent = "Deleting…";
      try {
        const res = await fetch(`/api/runs/${encodeURIComponent(RUN_ID)}`, { method: "DELETE" });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        window.location.href = "/home";
      } catch (e) {
        btn.disabled = false;
        btn.textContent = "Delete this analysis";
        zone.appendChild(el("p", "delete-err", "Could not delete: " + e.message));
      }
    });
    zone.appendChild(btn);
    root.appendChild(zone);
  }

  if (window.location.hash) {
    const node = document.querySelector(window.location.hash);
    if (node) {
      node.querySelector(".expand")?.classList.remove("hidden");
      node.scrollIntoView({ behavior: "smooth", block: "center" });
      node.classList.add("hilite");
      setTimeout(() => node.classList.remove("hilite"), 2200);
    }
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  RUN_ID = new URLSearchParams(window.location.search).get("run");
  if (!RUN_ID) {
    $("report").textContent = "";
    $("report").appendChild(el("div", "card runs-empty", "No analysis specified."));
    return;
  }
  $("script-link").href = `/script?run=${encodeURIComponent(RUN_ID)}`;
  $("replay-link").href = `/run?replay=1&record=${encodeURIComponent(RUN_ID)}`;
  $("onesheet-link").href = `/onesheet?run=${encodeURIComponent(RUN_ID)}`;
  $("binder-link").href = `/binder?run=${encodeURIComponent(RUN_ID)}`;
  try {
    renderReport(await fetchRecord(RUN_ID));
  } catch (e) {
    $("report").textContent = "";
    $("report").appendChild(el("div", "card runs-empty", "Could not load this report: " + e.message));
  }
});

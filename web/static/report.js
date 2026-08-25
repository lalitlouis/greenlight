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
    card.appendChild(diffBox("Before", diff, "del"));
    card.appendChild(diffBox("After", diff, "add"));
    const copy = el("button", "cite-toggle", "Copy the new text");
    copy.type = "button";
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(patch.replace);
        copy.textContent = "Copied ✓";
        setTimeout(() => { copy.textContent = "Copy the new text"; }, 2000);
      } catch { toast("Copy failed — select the text manually.", true); }
    });
    card.appendChild(copy);
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
  if (!IS_CASE && !f.rejection_reason && ["REPLACE", "CUT", "RESHOOT"].includes(r.action)) {
    ex.appendChild(fixControls(f));
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
    cuts.appendChild(el("div", "blk-label", `The cut list to ${pred.target || "your target"}`));
    const ol = el("ol");
    for (const b of pred.beats_to_cut) ol.appendChild(el("li", null, b));
    cuts.appendChild(ol);
    card.appendChild(cuts);
  }
  root.appendChild(card);
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
    tally.appendChild(cell);
  }
  head.appendChild(tally);
  root.appendChild(head);

  const drivers = (record.flags || [])
    .filter((f) => f.remedy?.est_cost_usd)
    .sort((a, b) => b.remedy.est_cost_usd[1] - a.remedy.est_cost_usd[1])
    .slice(0, 3);
  if (drivers.length && rep.est_clearance_cost_usd) {
    const card = el("div", "card drivers-card");
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
  secFlags.appendChild(el("h2", null, `Findings — ${cited.length}, every one cited`));
  root.appendChild(secFlags);
  const flags = el("div", "flags");
  cited.forEach((f) => flags.appendChild(flagRow(f, { expanded: f.severity === "BLOCKER" })));
  root.appendChild(flags);

  const rejectedFlags = record.rejected_flags || [];
  if (rejectedFlags.length) {
    const sec = el("div", "section-head");
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
  try {
    renderReport(await fetchRecord(RUN_ID));
  } catch (e) {
    $("report").textContent = "";
    $("report").appendChild(el("div", "card runs-empty", "Could not load this report: " + e.message));
  }
});

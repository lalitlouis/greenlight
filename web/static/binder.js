/* The Clearance Binder page: the standard Studio Clearance Log, rendered as a
   clean legal document — white paper, dense table, print-ready. Rows come from
   /api/binder/{id}; nothing is computed client-side. */

"use strict";

function bdRender(data) {
  const page = $("bd-page");
  page.textContent = "";

  const head = el("header", "bd-head");
  const left = el("div");
  left.appendChild(el("p", "bd-kicker", "Production clearance log"));
  left.appendChild(el("h1", "bd-title", data.title));
  const counts = data.counts || {};
  left.appendChild(
    el("p", "bd-sub",
      `Generated ${data.generated_at} · Greenlight Score ${data.score ?? "—"}/100 · ` +
      ["BLOCKER", "HIGH", "MEDIUM", "LOW", "FYI"]
        .filter((t) => counts[t])
        .map((t) => `${counts[t]} ${t.toLowerCase()}`)
        .join(", ") +
      (data.est_cost ? ` · est. exposure ${money(data.est_cost)}` : ""))
  );
  const d = data.draft || {};
  if (d.sha256) {
    const bits = [
      d.draft_date ? `draft ${d.draft_date}` : null,
      d.revision_label || null,
      d.pages ? `${d.pages} pp` : null,
      d.scene_numbers === "script" ? "script's own scene numbers" : "generated scene coordinates",
      `SHA-256 ${d.sha256.slice(0, 12)}…`,
    ].filter(Boolean);
    left.appendChild(el("p", "bd-draft", "This report is valid only for this draft: " + bits.join(" · ")));
  }
  head.appendChild(left);
  const brand = el("div", "bd-brand");
  brand.appendChild(el("span", "bd-dot"));
  brand.appendChild(brandName());
  head.appendChild(brand);
  page.appendChild(head);

  // Columns with no data in any row (e.g. Page on records without pagination)
  // are dropped rather than rendered as dead width.
  const cols = data.columns.filter((c) => data.rows.some((r) => String(r[c] ?? "").trim() !== ""));
  const colClass = (c) => "bd-col-" + c.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").split("-").slice(0, 2).join("-");
  const top = data.top_exposures || [];
  if (top.length) {
    const box = el("div", "bd-top");
    box.appendChild(el("p", "bd-top-title", "Top exposures — highest severity first"));
    const ul = el("ul", "bd-top-list");
    for (const t of top) {
      const li = el("li");
      li.appendChild(el("span", "bd-sevcell sev-" + t.severity, t.severity));
      // t.cost is a preformatted label: "5,000-20,000" wants a $; "no fee
      // expected" must not become "$no fee expected"
      const costTxt = t.cost ? (/^\d/.test(t.cost) ? ` · $${t.cost}` : ` · ${t.cost}`) : "";
      li.appendChild(document.createTextNode(` ${t.finding} — ${t.label} (${t.scene})` + costTxt));
      ul.appendChild(li);
    }
    box.appendChild(ul);
    page.appendChild(box);
  }

  const table = el("table", "bd-table");
  const thead = el("thead");
  const hr = el("tr");
  for (const c of cols) hr.appendChild(el("th", colClass(c), c));
  thead.appendChild(hr);
  table.appendChild(thead);
  const tbody = el("tbody");
  let lastScene = null;
  for (const row of data.rows) {
    const tr = el("tr", row.Severity ? "bd-sev-" + row.Severity : "bd-clear");
    const newScene = row.Scene !== lastScene;
    if (newScene && lastScene !== null) tr.classList.add("bd-scene-start");
    lastScene = row.Scene;
    const sceneCols = ["Scene", "Page", "Scene heading"];
    cols.forEach((c) => {
      const dup = sceneCols.includes(c) && !newScene;
      let val = dup ? "" : row[c];
      if (/^sources/i.test(c) && val) {
        // one source per line, wrap points after dots instead of mid-word
        val = String(val).replace(/;\s*/g, "\n").replace(/^www\./gm, "").replace(/\./g, ".\u200b");
      }
      const td = el("td", colClass(c), val);
      if (dup) td.classList.add("bd-dup");
      if (c === "Severity" && row[c]) { td.className = ""; td.classList.add(colClass(c), "bd-sevcell", "sev-" + row[c]); }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  page.appendChild(table);

  const bm = data.back_matter || {};
  const section = (title, node) => {
    page.appendChild(el("p", "bd-sec-title", title));
    page.appendChild(node);
  };
  const plainList = (items, render) => {
    const ul = el("ul", "bd-back-list");
    for (const it of items) ul.appendChild(render(it));
    return ul;
  };
  // The printed binder warns about incomplete desks and unexamined items
  // (pdfgen renders both) — the web binder must never be the quieter surface.
  for (const desk of bm.desks_incomplete || []) {
    const warn = el("div", "card run-error-banner");
    warn.appendChild(
      el("p", null, `${desk} desk did not complete — its findings are missing; ` +
        "do not treat its scenes as cleared. Rerun the analysis.")
    );
    page.appendChild(warn);
  }
  if ((bm.unexamined || []).length) {
    const warn = el("div", "card run-error-banner");
    warn.appendChild(
      el("p", null, `${bm.unexamined.length} item${bm.unexamined.length === 1 ? "" : "s"} ` +
        "extracted from the script were NOT examined by any desk — absence from " +
        "this log is not cleanliness.")
    );
    const ul = el("ul", "plain-list");
    for (const u of bm.unexamined) ul.appendChild(el("li", null, u));
    warn.appendChild(ul);
    page.appendChild(warn);
  }
  if (bm.rating && bm.rating.predicted) {
    const tgt = bm.rating.target && bm.rating.target !== bm.rating.predicted
      ? ` · production target ${bm.rating.target}` : "";
    section("Rating prediction", el("p", "bd-back-line", `Predicted ${bm.rating.predicted}${tgt} — full comparables panel in the web report.`));
  }
  if ((bm.cleared || []).length) {
    const det = document.createElement("details");
    const summ = document.createElement("summary");
    summ.textContent = `${bm.cleared.length} items examined and cleared — expand for the reasoning`;
    det.appendChild(summ);
    det.appendChild(plainList(bm.cleared, (it) => {
      const li = el("li");
      li.appendChild(el("span", "who", it.desk));
      li.appendChild(document.createTextNode(it.text));
      return li;
    }));
    section("Reviewed & cleared", det);
  }
  if ((bm.open_questions || []).length) {
    section("Open questions — honest unknowns", plainList(bm.open_questions, (it) => {
      const li = el("li");
      li.appendChild(el("span", "who", it.desk));
      li.appendChild(document.createTextNode(it.text));
      return li;
    }));
  }
  if ((bm.rejected || []).length) {
    section(`Rejected in verification (${bm.rejected.length}) — the cross-examination working`, plainList(bm.rejected, (it) => {
      const li = el("li");
      li.appendChild(el("span", "who", `${it.finding} ${it.category}`));
      li.appendChild(document.createTextNode(it.reason));
      return li;
    }));
  }
  if ((bm.adjudication || []).length) {
    section("Adjudication — merges and conflict resolutions", plainList(bm.adjudication, (t) => el("li", null, t)));
  }
  if ((bm.sources || []).length) {
    section("Sources cited", el("p", "bd-back-line", bm.sources.join(" · ")));
  }

  page.appendChild(el("p", "bd-disclaimer", data.disclaimer));
  document.title = `${data.title} — Clearance Binder`;
}

document.addEventListener("DOMContentLoaded", async () => {
  const id = new URLSearchParams(window.location.search).get("run");
  if (!id) {
    $("bd-page").textContent = "No analysis specified.";
    return;
  }
  $("bd-back").href = `/report?run=${encodeURIComponent(id)}`;
  $("bd-csv").href = `/api/binder/${encodeURIComponent(id)}.csv`;
  $("bd-pdf").href = `/api/binder/${encodeURIComponent(id)}.pdf`;
  try {
    const res = await fetch(`/api/binder/${encodeURIComponent(id)}`);
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    bdRender(await res.json());
  } catch (e) {
    $("bd-page").textContent = "Could not load: " + e.message;
  }
});

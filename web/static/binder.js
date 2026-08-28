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
      `${counts.BLOCKER || 0} blocker(s), ${counts.HIGH || 0} high, ${counts.MEDIUM || 0} medium` +
      (data.est_cost ? ` · est. exposure ${money(data.est_cost)}` : ""))
  );
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

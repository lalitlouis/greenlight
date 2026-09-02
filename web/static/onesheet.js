/* The ScriptRisk one-sheet: one page, the whole verdict. Deterministic render
   of a run record in the brand's dark "movie one-sheet" language — the artifact
   a producer pins to the wall or attaches to the E&O email. */

"use strict";

// labels come from the shared DESKS table (common.js); only the od- CSS
// class suffix is local
const DESK_CLASS = {
  clearance_counsel: "clearance",
  ratings_board: "ratings",
  safety_underwriter: "safety",
  territory_censor: "territory",
};

function osRender(record) {
  const rep = record.report || {};
  const counts = rep.counts || {};
  // null score is WITHHELD (a desk returned no dispositions) — it must never
  // render as a confident red 0/100 on the artifact meant for the E&O email.
  const withheld = rep.greenlight_score == null;
  const score = rep.greenlight_score ?? 0;
  const blockers = counts.BLOCKER || 0;
  const tone = withheld ? "mid" : blockers > 0 || score < 40 ? "bad" : score < 75 ? "mid" : "good";
  const page = $("os-page");
  page.textContent = "";

  const head = el("header", "os-head");
  const brand = el("div", "os-brand");
  brand.appendChild(el("span", "os-dot"));
  brand.appendChild(brandName());
  head.appendChild(brand);
  head.appendChild(el("span", "os-kind", "Production Risk One-Sheet"));
  page.appendChild(head);

  const hero = el("div", "os-hero");
  const left = el("div", "os-title-wrap");
  left.appendChild(el("h1", "os-title", record.script_title || "Untitled"));
  const verdict = withheld
    ? rep.verification_degraded
      ? "Score withheld — verification unavailable"
      : "Score withheld — analysis incomplete"
    : blockers > 0
      ? `Not cleared — ${blockers} blocker${blockers === 1 ? "" : "s"}`
      : tone === "good"
        ? "Cleared, with conditions"
        : "Conditional — remedies required";
  left.appendChild(el("p", "os-verdict v-" + tone, verdict));
  if (record.error) {
    left.appendChild(
      el("p", "os-verdict v-bad", "Run ended early — partial results; rerun before relying on this sheet.")
    );
  }
  const facts = el("p", "os-facts");
  facts.textContent =
    `${(record.flags || []).length} findings · ` +
    `${(record.rejected_flags || []).length} rejected in verification · ` +
    `${record.entity_accounting?.distinct ?? (record.entities || []).length} entities researched · ${rep.page_count || "—"} pages`;
  left.appendChild(facts);
  const cost = money(rep.est_clearance_cost_usd);
  if (cost) {
    const c = el("p", "os-cost");
    // two-path totals print wherever a total prints (parity with the report)
    const tgt = rep.est_cost_paths && rep.est_cost_paths.target_rating ? money(rep.est_cost_paths.target_rating) : null;
    if (tgt && tgt !== cost) {
      c.appendChild(document.createTextNode("Estimated clearance exposure as written "));
      c.appendChild(el("b", null, cost));
      c.appendChild(document.createTextNode(" · target-rating path "));
      c.appendChild(el("b", null, tgt));
    } else {
      c.appendChild(document.createTextNode("Estimated clearance exposure "));
      c.appendChild(el("b", null, cost));
    }
    left.appendChild(c);
  }
  // the quiet surface must not be the one that hides incompleteness
  const unex = record.unexamined || [];
  if (unex.length) {
    left.appendChild(el("p", "os-verdict v-bad", `${unex.length} extracted item${unex.length === 1 ? "" : "s"} NOT EXAMINED by any desk — those scenes are not cleared.`));
  }
  for (const desk of record.desks_incomplete || []) {
    left.appendChild(el("p", "os-verdict v-bad", `INCOMPLETE — the ${deskName(desk)} desk returned no dispositions; its scenes are not cleared.`));
  }
  const unverifiedN = (record.flags || []).filter((f) => f.verification_unavailable).length;
  if (unverifiedN) {
    left.appendChild(el("p", "os-verdict v-mid", `${unverifiedN} finding${unverifiedN === 1 ? "" : "s"} UNVERIFIED — the verifier could not run on ${unverifiedN === 1 ? "it" : "them"}; excluded from the score.`));
  }
  hero.appendChild(left);

  const ring = el("div", "score os-score " + tone);
  ring.style.setProperty("--scorepct", String(withheld ? 0 : score));
  ring.appendChild(el("b", null, withheld ? "—" : String(score)));
  ring.appendChild(el("span", "of", "/100"));
  hero.appendChild(ring);
  page.appendChild(hero);

  // four desks
  const dims = rep.dimension_scores || {};
  const deskRow = el("div", "os-desks");
  for (const [id, cls] of Object.entries(DESK_CLASS)) {
    const d = el("div", "os-desk od-" + cls);
    d.appendChild(el("b", null, dims[id] != null ? String(dims[id]) : "—"));
    d.appendChild(el("span", null, deskShort(id)));
    deskRow.appendChild(d);
  }
  page.appendChild(deskRow);

  // top findings by severity
  const sevRank = { BLOCKER: 0, HIGH: 1, MEDIUM: 2, LOW: 3, FYI: 4 };
  const top = [...(record.flags || [])]
    .sort((a, b) => (sevRank[a.severity] ?? 9) - (sevRank[b.severity] ?? 9))
    .slice(0, 3);
  if (top.length) {
    page.appendChild(el("div", "os-label", "Top findings"));
    const list = el("div", "os-flags");
    for (const f of top) {
      const row = el("div", "os-flag");
      row.appendChild(el("b", "os-sev sev-chip sev-" + f.severity, f.severity));
      const main = el("div", "os-flag-main");
      main.appendChild(el("span", "os-flag-cat", prettyCat(f.category)));
      if (f.verification_unavailable) {
        main.appendChild(el("span", "sev-chip chip-partial", f.verification_blocked ? "unverified — blocked by the platform content filter" : "unverified — verifier unavailable"));
      }
      // the marker is a chip, not raw bracket text in the finding line
      let txt = f.finding || "";
      if (txt.startsWith("[partially supported] ")) {
        txt = txt.slice("[partially supported] ".length);
        main.appendChild(el("span", "sev-chip chip-partial", "PARTIAL — verified with caveats"));
      }
      main.appendChild(el("span", "os-flag-txt", txt.slice(0, 170) + (txt.length > 170 ? "…" : "")));
      row.appendChild(main);
      const right = el("div", "os-flag-right");
      // cost lives at remedy.est_cost_usd; the flat est_cost_usd_* names are
      // tool-call arguments that never reach the record (every row read
      // "cost TBD" under the page's own exposure total)
      const fc = money((f.remedy || {}).est_cost_usd);
      right.appendChild(el("b", null, fc || "cost TBD"));
      right.appendChild(el("span", null, `${(f.citations || []).length} citations`));
      row.appendChild(right);
      list.appendChild(row);
    }
    page.appendChild(list);
  }

  // rating strip
  const pred = rep.rating_prediction || {};
  if (pred.predicted) {
    const strip = el("div", "os-rating");
    strip.appendChild(el("b", "rating-badge sm r-" + pred.predicted, pred.predicted));
    const rtxt = el("div", "os-rating-txt");
    const comps = pred.comparables || [];
    // "at or stricter", the same count the one-sheet PDF and the report print —
    // this page once counted exact matches only, so two one-sheets disagreed
    const ORDER = ["G", "PG", "PG-13", "R", "NC-17"];
    const predIdx = ORDER.indexOf(pred.predicted);
    const atOrAbove = predIdx >= 0
      ? comps.filter((c) => ORDER.indexOf(c.rating) >= predIdx).length
      : comps.filter((c) => c.rating === pred.predicted).length;
    rtxt.appendChild(
      el("span", "os-rating-line",
        `Predicted ${pred.predicted}${pred.target && pred.target !== pred.predicted ? " · production target " + pred.target : ""} — ${atOrAbove} of ${comps.length} nearest released comparables rate ${pred.predicted} or stricter`)
    );
    if (pred.rationale) rtxt.appendChild(el("span", "os-rating-why", pred.rationale));
    strip.appendChild(rtxt);
    page.appendChild(strip);
  }

  const foot = el("footer", "os-foot");
  const when = (record.generated_at || "").slice(0, 10);
  foot.appendChild(el("span", null, `scriptrisk.com · generated ${when}`));
  foot.appendChild(el("span", null, "Every finding cited and independently verified · research tool, not legal advice"));
  page.appendChild(foot);

  document.title = `${record.script_title || "One-Sheet"} — ScriptRisk One-Sheet`;
}

document.addEventListener("DOMContentLoaded", async () => {
  const id = new URLSearchParams(window.location.search).get("run");
  if (!id) {
    $("os-page").textContent = "No analysis specified.";
    return;
  }
  $("os-back").href = `/report?run=${encodeURIComponent(id)}`;
  $("os-pdf").href = `/api/onesheet/${encodeURIComponent(id)}.pdf`;
  try {
    osRender(await fetchRecord(id));
  } catch (e) {
    $("os-page").textContent = "Could not load: " + e.message;
  }
});

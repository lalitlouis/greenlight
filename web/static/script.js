/* Marked-up script page: the original fountain source sliced by raw_span, flags in
   the gutter. raw_span offsets index the exact source the parser saw — the report
   and the script are one object. */

"use strict";

let RUN_ID = null;

function worstSeverity(flags) {
  for (const sev of SEVS) if (flags.some((f) => f.severity === sev)) return sev;
  return null;
}

function renderScript(record, data) {
  const root = $("script");
  root.textContent = "";
  $("script-title").textContent = data.title || record.script_title || "Script";

  const byScene = {};
  for (const f of (record.flags || []).filter((x) => (x.citations || []).length > 0)) {
    for (const sid of f.scene_ids || []) (byScene[sid] = byScene[sid] || []).push(f);
  }

  const view = el("div", "scriptview");
  for (const scene of data.scenes) {
    const flags = byScene[scene.scene_id] || [];
    const worst = worstSeverity(flags);
    const row = el("div", "card scene-row" + (worst ? " flagged-" + worst : ""));
    row.id = "scene-" + scene.scene_id;

    const text = el("pre", "scene-text");
    text.appendChild(el("span", "sid", `${scene.scene_id} · p.${scene.page}`));
    text.appendChild(
      document.createTextNode(data.source.slice(scene.raw_span[0], scene.raw_span[1]).trimEnd())
    );
    row.appendChild(text);

    const gutter = el("div", "gutter");
    for (const f of flags) {
      const note = el("div", "gnote gn-" + f.severity);
      note.appendChild(
        el("span", "gt", `${f.severity} · ${f.flag_id} · ${prettyCat(f.category)}`)
      );
      note.appendChild(
        el(
          "p",
          null,
          (f.finding || "").slice(0, 180) + ((f.finding || "").length > 180 ? "…" : "")
        )
      );
      note.title = "Open in report";
      note.addEventListener("click", () => {
        window.location.href = `/report?run=${encodeURIComponent(RUN_ID)}#flag-${f.flag_id}`;
      });
      gutter.appendChild(note);
    }
    row.appendChild(gutter);
    view.appendChild(row);
  }
  root.appendChild(view);

  if (window.location.hash) {
    const node = document.querySelector(window.location.hash);
    if (node) {
      node.scrollIntoView({ behavior: "smooth", block: "start" });
      node.classList.add("hilite");
      setTimeout(() => node.classList.remove("hilite"), 2200);
    }
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  RUN_ID = new URLSearchParams(window.location.search).get("run");
  if (!RUN_ID) return;
  $("report-link").href = `/report?run=${encodeURIComponent(RUN_ID)}`;
  try {
    const [record, res] = await Promise.all([
      fetchRecord(RUN_ID),
      fetch(`/api/script/${encodeURIComponent(RUN_ID)}`),
    ]);
    if (!res.ok) throw new Error("script source unavailable");
    renderScript(record, await res.json());
  } catch (e) {
    $("script").textContent = "";
    $("script").appendChild(el("div", "card runs-empty", "Could not load: " + e.message));
  }
});

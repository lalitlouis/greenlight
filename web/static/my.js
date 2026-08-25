/* My reports: the signed-in user's history — open or delete. */

"use strict";

const STALL_MS = 30 * 60 * 1000;

function rowFor(r) {
  const row = el("div", "card my-row");
  const started = Date.parse((r.generated_at || "").replace(/([+-]\d{2})(\d{2})$/, "$1:$2"));
  const stalled = r.status === "running" && started && Date.now() - started > STALL_MS;
  const running = r.status === "running" && !stalled;
  const liveHref = r.kind === "writer" ? `/writer?run=${encodeURIComponent(r.id)}` : `/run?id=${encodeURIComponent(r.id)}`;
  const doneHref = r.kind === "writer" ? `/writer?run=${encodeURIComponent(r.id)}` : `/report?run=${encodeURIComponent(r.id)}`;
  const main = el("div", "my-main");
  const title = el("a", "my-title", r.title || r.id);
  title.href = running ? liveHref : doneHref;
  main.appendChild(title);
  const meta = el("p", "my-meta");
  const bits = [r.kind === "writer" ? "Writer's Room" : "Clearance report", fmtDate(r.generated_at)];
  if (running) bits.push("running now");
  if (stalled) bits.push("stalled — safe to delete");
  if (r.status === "error") bits.push("failed");
  if (r.score != null) bits.push(`score ${r.score}/100`);
  if (r.verdict) bits.push(r.verdict);
  if (r.flags) bits.push(`${r.flags} findings`);
  meta.textContent = bits.filter(Boolean).join(" · ");
  main.appendChild(meta);
  row.appendChild(main);

  if (running) {
    const badge = el("span", "my-running");
    badge.appendChild(el("span", "pulse"));
    badge.appendChild(el("span", null, "Running"));
    row.appendChild(badge);
  }
  const open = el("a", "btn btn-secondary", running ? "Watch live" : "Open");
  open.href = title.href;
  row.appendChild(open);
  if (running) return row;

  const del = el("button", "btn btn-danger", "Delete");
  del.type = "button";
  del.addEventListener("click", async () => {
    if (!confirm(`Delete "${r.title}" permanently? The report and script text are removed.`)) return;
    const res = await fetch(`/api/my/runs/${encodeURIComponent(r.id)}`, { method: "DELETE" });
    if (res.ok) {
      row.remove();
      toast("Deleted.");
    } else {
      toast("Could not delete: " + (await res.text()), true);
    }
  });
  row.appendChild(del);
  return row;
}

document.addEventListener("DOMContentLoaded", async () => {
  const list = $("my-list");
  try {
    const res = await fetch("/api/my/runs");
    if (res.status === 401) {
      list.textContent = "";
      const card = el("div", "card runs-empty");
      card.appendChild(el("p", null, "Sign in to see your reports."));
      const a = el("a", "btn btn-primary", "Sign in with Google");
      a.href = "/auth/login";
      card.appendChild(a);
      list.appendChild(card);
      return;
    }
    const runs = await res.json();
    list.textContent = "";
    if (!runs.length) {
      list.appendChild(
        el("div", "card runs-empty", "No reports yet — analyses you run while signed in will appear here.")
      );
      return;
    }
    for (const r of runs) list.appendChild(rowFor(r));
  } catch (e) {
    list.textContent = "";
    list.appendChild(el("div", "card runs-empty", "Could not load your reports."));
  }
});

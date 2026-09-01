/* My reports: the signed-in user's history — open or delete. */

"use strict";

const STALL_MS = 30 * 60 * 1000;

function rowFor(r) {
  const row = el("div", "card my-row");
  const started = Date.parse((r.generated_at || "").replace(/([+-]\d{2})(\d{2})$/, "$1:$2"));
  const stalled = r.status === "running" && !r.live && started && Date.now() - started > STALL_MS;
  const running = r.status === "running" && !stalled;
  if (!r.id || r.id === "undefined") return null;  // a ledger stub without an id can neither open nor delete
  const liveHref = r.kind === "writer" ? `/writer?run=${encodeURIComponent(r.id)}` : `/run?id=${encodeURIComponent(r.id)}`;
  const doneHref = r.kind === "writer" ? `/writer?run=${encodeURIComponent(r.id)}` : `/report?run=${encodeURIComponent(r.id)}`;
  const main = el("div", "my-main");
  const title = el("a", "my-title", r.title || r.id);
  if (r.status === "stopped") title.removeAttribute("href");
  else title.href = running ? liveHref : doneHref;
  main.appendChild(title);
  const meta = el("p", "my-meta");
  const bits = [r.kind === "writer" ? "Writer's Room" : "Clearance report", fmtDate(r.generated_at)];
  if (running) bits.push("running now");
  if (stalled) bits.push("stalled — safe to delete");
  if (r.status === "error") bits.push("failed");
  if (r.status === "stopped") bits.push("stopped — no report was produced");
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
  if (r.status !== "stopped") {
    // a stopped run produced no report — nothing to open
    const open = el("a", "btn btn-secondary", running ? "Watch live" : "Open");
    open.href = title.href;
    row.appendChild(open);
  }
  if (running) {
    const stop = el("button", "btn btn-danger", "Stop");
    stop.type = "button";
    stop.addEventListener("click", async () => {
      const sure = await confirmDialog({
        title: `Stop "${r.title || r.id}"?`,
        message:
          "The analysis is cancelled cleanly and no report is produced. " +
          "Work already done is discarded. This cannot be resumed.",
        confirmLabel: "Stop the analysis",
        danger: true,
      });
      if (!sure) return;
      stop.disabled = true;
      stop.textContent = "Stopping…";
      try {
        const res = await fetch(`/api/my/runs/${encodeURIComponent(r.id)}/stop`, {
          method: "POST",
        });
        if (!res.ok) throw new Error(String(res.status));
        window.location.reload();
      } catch {
        stop.disabled = false;
        stop.textContent = "Stop";
      }
    });
    row.appendChild(stop);
    return row;
  }

  const del = el("button", "btn btn-danger", "Delete");
  del.type = "button";
  del.addEventListener("click", async () => {
    const sure = await confirmDialog({
      title: `Delete "${r.title || r.id}"?`,
      message: "The report and your uploaded script are removed from our storage permanently. This cannot be undone.",
      confirmLabel: "Delete permanently",
      danger: true,
    });
    if (!sure) return;
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
    for (const r of runs) { const node = rowFor(r); if (node) list.appendChild(node); }
  } catch (e) {
    list.textContent = "";
    list.appendChild(el("div", "card runs-empty", "Could not load your reports."));
  }
});

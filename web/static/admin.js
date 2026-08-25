/* Admin console: renders /api/admin/overview, refreshed on a timer. */

"use strict";

function cell(tr, text, mono) {
  const td = el("td", mono ? "adm-mono" : null, text == null ? "" : String(text));
  tr.appendChild(td);
  return td;
}

function renderOverview(o) {
  const pulse = $("adm-pulse");
  pulse.textContent = "";
  const m = o.metrics || {};
  const items = [
    [m.runs, "clearance runs (since boot)"],
    [m.writer_runs, "writer runs"],
    [m.fixes, "fix drafts"],
    [m.errors, "errors"],
  ];
  for (const [v, label] of items) {
    const div = el("div");
    div.appendChild(el("b", null, String(v ?? 0)));
    div.appendChild(el("span", null, label));
    pulse.appendChild(div);
  }
  $("adm-sub").textContent =
    `Instance up ${Math.floor((m.uptime_s || 0) / 60)}m · assets ${m.asset_version || "?"} · ` +
    `refreshes every 10 seconds.`;

  const live = $("adm-live");
  live.textContent = "";
  const running = [
    ...(o.live?.clearance || []).map((r) => `clearance ${r.id} — ${r.status}`),
    ...(o.live?.writer || []).map((r) => `writer ${r.id} — ${r.status} (${r.stage || ""})`),
  ];
  live.appendChild(
    el("p", null, running.length ? running.join(" · ") : "Nothing running right now.")
  );

  const users = $("adm-users");
  users.textContent = "";
  let tr = el("tr");
  for (const h of ["User", "Email", "Runs", "Latest", "When"]) tr.appendChild(el("th", null, h));
  users.appendChild(tr);
  for (const u of o.users || []) {
    tr = el("tr");
    cell(tr, u.name || u.sub);
    cell(tr, u.email || "—");
    cell(tr, u.runs);
    cell(tr, u.latest_title);
    cell(tr, fmtDate(u.latest_at));
    users.appendChild(tr);
  }
  if ((o.users || []).length === 0) {
    tr = el("tr");
    cell(tr, "No signed-in users yet.");
    users.appendChild(tr);
  }

  const logs = $("adm-logs");
  logs.textContent = "";
  tr = el("tr");
  for (const h of ["Time", "Kind", "Detail"]) tr.appendChild(el("th", null, h));
  logs.appendChild(tr);
  for (const entry of o.logs || []) {
    tr = el("tr");
    if ((entry.level || "") === "error" || entry.kind === "http_error") tr.className = "adm-err";
    cell(tr, entry.ts, true);
    cell(tr, entry.kind + (entry.event ? " · " + entry.event : ""), true);
    const rest = Object.entries(entry)
      .filter(([k]) => !["ts", "kind", "event"].includes(k))
      .map(([k, v]) => `${k}=${v}`)
      .join("  ");
    cell(tr, rest, true);
    logs.appendChild(tr);
  }
}

async function refresh() {
  try {
    const res = await fetch("/api/admin/overview");
    if (!res.ok) {
      $("adm-sub").textContent = "Not authorized.";
      return;
    }
    renderOverview(await res.json());
  } catch {
    /* transient; next tick retries */
  }
}

document.addEventListener("DOMContentLoaded", () => {
  refresh();
  setInterval(refresh, 10000);
});

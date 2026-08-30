/* Admin console: renders /api/admin/overview, refreshed on a timer. */

"use strict";

function cell(tr, text, mono) {
  const td = el("td", mono ? "adm-mono" : null, text == null ? "" : String(text));
  tr.appendChild(td);
  return td;
}

function fmtElapsed(s) {
  if (s == null) return "—";
  return s >= 60 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${Math.round(s)}s`;
}

function renderOverview(o) {
  const pulse = $("adm-pulse");
  pulse.textContent = "";
  const m = o.metrics || {};
  const lt = o.lifetime || {};
  const items = [
    [lt.runs ?? 0, `clearance runs all-time (${m.runs ?? 0} since boot)`],
    [lt.writer_runs ?? 0, `writer runs all-time (${m.writer_runs ?? 0})`],
    [lt.fixes ?? 0, `fix drafts all-time (${m.fixes ?? 0})`],
    [lt.errors ?? 0, `errors all-time (${m.errors ?? 0})`],
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
  // Fleet (Firestore) is the truth for clearance runs; writer runs still come
  // from this instance's memory.
  const running = [
    ...(o.fleet || [])
      .filter((r) => r.status === "running")
      .map((r) => `clearance ${r.id} — ${r.owner || "anon"} · ${fmtElapsed(r.elapsed_s)}`),
    ...(o.live?.writer || []).map((r) => `writer ${r.id} — ${r.status} (${r.stage || ""})`),
  ];
  live.appendChild(
    el("p", null, running.length ? running.join(" · ") : "Nothing running right now.")
  );

  const fleet = $("adm-fleet");
  fleet.textContent = "";
  let tr = el("tr");
  for (const h of ["Run", "Title", "Owner", "Status", "Started", "Duration"])
    tr.appendChild(el("th", null, h));
  fleet.appendChild(tr);
  for (const r of o.fleet || []) {
    tr = el("tr");
    if (r.status === "error") tr.className = "adm-err";
    cell(tr, r.id, true);
    cell(tr, r.title || "—");
    cell(tr, r.owner || "—");
    cell(tr, r.status);
    cell(tr, r.started_at ? fmtDate(new Date(r.started_at * 1000).toISOString()) : "—");
    cell(tr, fmtElapsed(r.elapsed_s), true);
    fleet.appendChild(tr);
  }
  if ((o.fleet || []).length === 0) {
    tr = el("tr");
    cell(tr, "No runs recorded yet.");
    fleet.appendChild(tr);
  }

  const users = $("adm-users");
  users.textContent = "";
  tr = el("tr");
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

/* Kill switch: pauses NEW analysis starts fleet-wide; in-flight runs finish. */
async function hydratePause() {
  const input = document.getElementById("adm-pause-input");
  const note = document.getElementById("adm-pause-note");
  if (!input) return;
  const paint = (paused) => {
    input.checked = paused;
    note.textContent = paused ? "Paused" : "";
    note.classList.toggle("adm-paused", paused);
  };
  try {
    const r = await (await fetch("/api/admin/pause")).json();
    paint(!!r.paused);
  } catch {
    note.textContent = "unavailable";
    input.disabled = true;
    return;
  }
  input.addEventListener("change", async () => {
    input.disabled = true;
    try {
      const r = await (
        await fetch("/api/admin/pause", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paused: input.checked }),
        })
      ).json();
      paint(!!r.paused);
    } catch {
      paint(!input.checked);
      note.textContent = "failed";
    } finally {
      input.disabled = false;
    }
  });
}
hydratePause();

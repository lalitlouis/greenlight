"""The Legal Clearance Binder: the run's findings re-shaped into the standard
Studio Clearance Log a production legal team actually files —
Scene | Item | Category | Status | Note — plus a citation appendix.

Deterministic: every row is derived from the record; nothing is generated.
Status language is deliberately conservative — this tool flags, it does not
clear, so the strongest positive a row can say is "No known issue".
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from typing import Any

STATUS_BY_SEVERITY = {
    "BLOCKER": "DO NOT SHOOT AS WRITTEN — clearance/mitigation required",
    "HIGH": "License / mitigation required",
    "MEDIUM": "Review required",
    "LOW": "Note for file",
    "FYI": "Note for file",
}

COLUMNS = [
    "Scene",
    "Page",
    "Scene heading",
    "Item",
    "Category",
    "Severity",
    "Clearance status",
    "Remedy / licensing note",
    "Est. cost (USD)",
    "Sources",
    "Finding",
]


def _pretty(slug: str) -> str:
    return (slug or "").replace("_", " ").strip().capitalize()


def _scene_sort_key(sid: str) -> tuple[int, str]:
    digits = "".join(ch for ch in sid if ch.isdigit())
    return (int(digits) if digits else 10_000, sid)


def build(record: dict[str, Any], scene_meta: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The binder as data: header block + one row per finding per scene, with
    explicit no-known-issue rows so the log covers the whole script."""
    entities = {e.get("entity_id"): e.get("surface") for e in record.get("entities", [])}
    by_scene: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in record.get("flags", []):
        if not f.get("citations"):
            continue  # the invariant, applied here too: uncited findings do not exist
        for sid in f.get("scene_ids") or ["(script-wide)"]:
            by_scene[sid].append(f)

    all_sids = sorted(set(scene_meta) | set(by_scene), key=_scene_sort_key)
    rows: list[dict[str, str]] = []
    for sid in all_sids:
        meta = scene_meta.get(sid, {})
        base = {
            "Scene": sid,
            "Page": str(meta.get("page", "")),
            "Scene heading": meta.get("heading", ""),
        }
        flags = sorted(
            by_scene.get(sid, []),
            key=lambda f: list(STATUS_BY_SEVERITY).index(f.get("severity", "FYI")),
        )
        if not flags:
            rows.append(
                {
                    **base,
                    "Item": "—",
                    "Category": "—",
                    "Severity": "",
                    "Clearance status": "No known issue",
                    "Remedy / licensing note": "",
                    "Est. cost (USD)": "",
                    "Sources": "",
                    "Finding": "",
                }
            )
            continue
        for f in flags:
            r = f.get("remedy") or {}
            note_parts = []
            if r.get("action"):
                note_parts.append(r["action"].replace("_", " ").title())
            if r.get("detail"):
                note_parts.append(r["detail"])
            cost = r.get("est_cost_usd") or []
            cost_pair = len(cost) == 2  # noqa: PLR2004 - [low, high]
            valid = cost_pair and all(isinstance(c, int | float) and c >= 0 for c in cost)
            cost_s = f"{cost[0]:,}-{cost[1]:,}" if valid else ""
            hosts = []
            for c in f.get("citations", []):
                host = (c.get("url") or "").split("/")[2:3]
                if host and host[0] not in hosts:
                    hosts.append(host[0])
            rows.append(
                {
                    **base,
                    "Item": entities.get(f.get("entity_id")) or _pretty(f.get("category", "")),
                    "Category": _pretty(f.get("category", "")),
                    "Severity": f.get("severity", ""),
                    "Clearance status": STATUS_BY_SEVERITY.get(f.get("severity", ""), "Review"),
                    "Remedy / licensing note": " — ".join(note_parts)[:400],
                    "Est. cost (USD)": cost_s,
                    "Sources": "; ".join(hosts[:4]),
                    "Finding": f.get("flag_id", ""),
                }
            )

    rep = record.get("report") or {}
    return {
        "title": record.get("script_title") or "Untitled",
        "generated_at": (record.get("generated_at") or "")[:10],
        "score": rep.get("greenlight_score"),
        "counts": rep.get("counts") or {},
        "est_cost": rep.get("est_clearance_cost_usd"),
        "columns": COLUMNS,
        "rows": rows,
        "disclaimer": (
            "Prepared by ScriptRisk (scriptrisk.com). Research tool output, not legal advice; "
            "'No known issue' means no finding survived independent verification, not a legal "
            "clearance. Every flagged row cites public sources available in the full report."
        ),
    }


def to_csv(binder: dict[str, Any]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS)
    buf.write(f"# {binder['title']} — Clearance Log — generated {binder['generated_at']}\n")
    buf.write(f"# {binder['disclaimer']}\n")
    w.writeheader()
    for row in binder["rows"]:
        w.writerow(row)
    return buf.getvalue()

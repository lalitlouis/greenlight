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


def _fold_territory_rows(flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One binder row per territory ISSUE: territory_cn_drug_use and
    territory_uae_drug_use on the same scenes fold into a single row whose
    category reads "Territory (CN, UAE): Drug Use" — the per-desk flags stay
    separate in the full report; the log is a scannable summary."""
    import re as _re

    grouped: dict[tuple, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for f in flags:
        m = _re.match(r"territory_([a-z]{2,3})_(.+)", f.get("category", ""))
        if not m:
            out.append(f)
            continue
        cc, issue = m.group(1).upper(), m.group(2)
        if issue in grouped:
            g = grouped[issue]
            if cc not in g["_territories"]:
                g["_territories"].append(cc)
            g["_all_scenes"] = sorted(
                set(g.get("_all_scenes") or []) | set(f.get("_all_scenes") or []),
                key=_scene_sort_key,
            )
            sev_order = list(STATUS_BY_SEVERITY)
            if sev_order.index(f.get("severity", "FYI")) < sev_order.index(
                g.get("severity", "FYI")
            ):
                g["severity"] = f.get("severity")
        else:
            g = {**f, "_territories": [cc], "_issue": issue}
            grouped[issue] = g
            out.append(g)
    for g in out:
        if "_territories" in g:
            tcs = ", ".join(g["_territories"])
            issue_label = g["_issue"].replace("_", " ").title()
            g["category"] = f"Territory ({tcs}): {issue_label}"
    return out


def _clip(text: str, limit: int = 480) -> str:
    """Cap a note at a word boundary — a mid-word slice reads as a data bug."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:—-") + " …"


def _label(f: dict[str, Any]) -> str:
    cat = f.get("category", "")
    return cat if cat.startswith("Territory (") else _pretty(cat)


def _pretty(slug: str) -> str:
    return (slug or "").replace("_", " ").strip().capitalize()


def _ranges(nums: list[int]) -> list[str]:
    chunks: list[str] = []
    start = prev = nums[0]
    for n in [*nums[1:], None]:
        if n is not None and n == prev + 1:
            prev = n
            continue
        chunks.append(f"S{start:03d}" if start == prev else f"S{start:03d}-S{prev:03d}")
        if n is not None:
            start = prev = n
    return chunks


def _compact_scene_ref(sids: list[str], cap: int = 6) -> str:
    """S003, S004, S005 -> "S003-S005"; beyond `cap` chunks, "+N more".
    A 20-scene list stacked vertically made the PDF unscannable."""
    nums = []
    for s in sids:
        try:
            nums.append(int(s.lstrip("S")))
        except ValueError:
            return ", ".join(sids[:cap]) + (f" +{len(sids) - cap} more" if len(sids) > cap else "")
    chunks = _ranges(sorted(nums))
    if len(chunks) > cap:
        return ", ".join(chunks[:cap]) + f" +{len(chunks) - cap} more"
    return ", ".join(chunks)


def _scene_sort_key(sid: str) -> tuple[int, str]:
    digits = "".join(ch for ch in sid if ch.isdigit())
    return (int(digits) if digits else 10_000, sid)


def _cost_label(cost: list[Any]) -> str:
    pair = len(cost) == 2  # noqa: PLR2004 - [low, high]
    if not (pair and all(isinstance(c, int | float) and c >= 0 for c in cost)):
        return ""
    if cost[0] == 0 and cost[1] == 0:
        return "no fee expected"
    return f"{cost[0]:,}-{cost[1]:,}"


def build(record: dict[str, Any], scene_meta: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The binder as data: header block + one row per finding per scene, with
    explicit no-known-issue rows so the log covers the whole script."""
    entities = {e.get("entity_id"): e.get("surface") for e in record.get("entities", [])}
    # One line item per finding, anchored at its first scene with a multi-scene
    # reference — repeating a finding per scene reads as duplicate exposure and
    # artificially inflates the log.
    by_scene: dict[str, list[dict[str, Any]]] = defaultdict(list)
    touched: set[str] = set()
    for f in record.get("flags", []):
        if not f.get("citations"):
            continue  # the invariant, applied here too: uncited findings do not exist
        sids = sorted(f.get("scene_ids") or ["(script-wide)"], key=_scene_sort_key)
        touched.update(sids)
        by_scene[sids[0]].append({**f, "_all_scenes": sids})

    all_sids = sorted(set(scene_meta) | touched, key=_scene_sort_key)
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
        if not flags and sid in touched:
            continue  # covered by a finding anchored at an earlier scene
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
        flags = _fold_territory_rows(flags)
        for f in flags:
            all_sids_f = f.get("_all_scenes") or [sid]
            scene_ref = _compact_scene_ref(all_sids_f)
            r = f.get("remedy") or {}
            note_parts = []
            if r.get("action"):
                note_parts.append(r["action"].replace("_", " ").title())
            if r.get("detail"):
                note_parts.append(r["detail"])
            cost_s = _cost_label(r.get("est_cost_usd") or [])
            hosts = []
            for c in f.get("citations", []):
                host = (c.get("url") or "").split("/")[2:3]
                if host and host[0] not in hosts:
                    hosts.append(host[0])
            rows.append(
                {
                    **base,
                    "Scene": scene_ref,
                    "Item": entities.get(f.get("entity_id")) or _label(f),
                    "Category": _label(f),
                    "Severity": f.get("severity", ""),
                    "Clearance status": STATUS_BY_SEVERITY.get(f.get("severity", ""), "Review"),
                    "Remedy / licensing note": _clip(" — ".join(note_parts)),
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

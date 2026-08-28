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


def _territory_label(category: str) -> str:
    """territory_cn_drug_use -> "Territory (CN): Drug Use"."""
    import re as _re

    m = _re.match(r"territory_([a-z]{2,3})_(.+)", category or "")
    if not m:
        return ""
    return f"Territory ({m.group(1).upper()}): {m.group(2).replace('_', ' ').title()}"


def _clip(text: str, limit: int = 480) -> str:
    """Cap a note at a word boundary — a mid-word slice reads as a data bug."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:—-") + " …"


def _label(f: dict[str, Any]) -> str:
    cat = f.get("category", "")
    if cat.startswith("Territory ("):
        return cat
    return _territory_label(cat) or _pretty(cat)


def _unescape(text: str) -> str:
    import html

    return html.unescape(text or "")


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


NOTE_CEILING = 2400  # guard against pathological output only — nothing real elides


def _note(f: dict[str, Any]) -> str:
    r = f.get("remedy") or {}
    note_parts = []
    if f.get("finding"):
        note_parts.append(str(f["finding"]))
    remedy_bits = []
    if r.get("action"):
        remedy_bits.append(r["action"].replace("_", " ").title())
    if r.get("detail"):
        remedy_bits.append(r["detail"])
    if remedy_bits:
        note_parts.append("Remedy: " + " — ".join(remedy_bits))
    return _clip("\n".join(note_parts), NOTE_CEILING)


BACKGROUND_HOSTS = {
    "wikipedia.org",
    "fandom.com",
    "reddit.com",
    "quora.com",
    "discogs.com",
    "songfacts.com",
    "secondhandsongs.com",
    "imdb.com",
    "tvtropes.org",
    "writing.stackexchange.com",
    "writingforums.com",
    "genius.com",
}


def _tier_label(host: str) -> str:
    bare = host.removeprefix("www.")
    root = ".".join(bare.split(".")[-2:])
    return f"{bare} (background)" if bare in BACKGROUND_HOSTS or root in BACKGROUND_HOSTS else bare


def _hosts(f: dict[str, Any]) -> list[str]:
    hosts: list[str] = []
    for c in f.get("citations", []):
        seg = (c.get("url") or "").split("/")[2:3]
        host = _tier_label(seg[0]) if seg else ""
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def _scene_ref(sids: list[str], numbers: dict[str, str]) -> str:
    """Prefer the script's own locked numbers — the coordinate system every
    production department shares. Generated S### ids compact into ranges."""
    if sids and all(numbers.get(sid) for sid in sids):
        labels = list(dict.fromkeys(numbers[sid] for sid in sids))
        cap = 6
        shown = ", ".join(labels[:cap])
        more = f" +{len(labels) - cap} more" if len(labels) > cap else ""
        return f"Sc. {shown}{more}"
    return _compact_scene_ref(sids)


def _flag_row(
    f: dict[str, Any],
    base: dict[str, str],
    entities: dict[str, Any],
    sid: str,
    numbers: dict[str, str],
) -> dict[str, str]:
    item = _unescape(entities.get(f.get("entity_id")) or "")
    return {
        **base,
        "Scene": _scene_ref(f.get("_all_scenes") or [sid], numbers),
        "Item": item or "\u2014",
        "Category": _label(f),
        "Severity": f.get("severity", ""),
        "Clearance status": STATUS_BY_SEVERITY.get(f.get("severity", ""), "Review"),
        "Remedy / licensing note": _note(f),
        "Est. cost (USD)": _cost_label((f.get("remedy") or {}).get("est_cost_usd") or []),
        "Sources": "\n".join(_hosts(f)[:4]),
        "Finding": f.get("flag_id", ""),
    }


_DETERMINATION_NEG = (
    "unclear",
    "unresolved",
    "unknown",
    "unable",
    "couldn't",
    "could not",
    "pending",
    "unverified",
    "needs further",
    "needs manual",
    "open question",
)


def _is_determination(q: str) -> bool:
    """A note that states a closed conclusion ("Cleared.", "no license
    required") rather than an unresolved item. Mirrors report.js."""
    import re as _re

    t = str(q)
    if t.rstrip().endswith("?"):
        return False
    low = t.lower()
    if any(neg in low for neg in _DETERMINATION_NEG):
        return False
    if _re.search(r"\bcleared\b", low):
        return True
    return bool(
        _re.search(
            r"\bno (?:synchronization|sync|master(?:[- ]use)?|licen[cs]e|clearance"
            r"|release|permit|action)\b[^.?]*\b(?:required|needed|necessary)\b",
            low,
        )
    )


def _back_matter(record: dict[str, Any]) -> dict[str, Any]:
    """Everything the report knows beyond the findings table — the binder is
    the artifact that reaches production counsel, so the verifier rejections,
    the adjudication, and the cleared determinations travel with it."""
    oq_all = [(desk, q) for desk, qs in (record.get("open_questions") or {}).items() for q in qs]
    rep = record.get("report") or {}
    pred = rep.get("rating_prediction") or {}
    hosts: list[str] = []
    for f in record.get("flags", []):
        for h in _hosts(f):
            if h not in hosts:
                hosts.append(h)
    ents = {e.get("entity_id"): e.get("surface") for e in record.get("entities", [])}
    # Group by entity: four desks each clearing the same prop is one row with
    # four determinations, not four rows (mirrors report.js clearedRows).
    by_entity: dict[str, list[tuple[str, str]]] = {}
    script_level: list[dict[str, Any]] = []
    for d, items in (record.get("cleared") or {}).items():
        for c in items:
            who = _unescape(ents.get(c.get("entity_id")) or "")
            reasoning = c.get("reasoning", "")
            if who:
                by_entity.setdefault(who, []).append((_pretty(d), reasoning))
            else:
                script_level.append({"desk": _pretty(d), "text": reasoning})
    recorded = [
        (
            {"desk": ds[0][0], "text": f"{who}: {ds[0][1]}"}
            if len(ds) == 1
            else {
                "desk": ", ".join(dict.fromkeys(d for d, _ in ds)),
                "text": f"{who} — " + " · ".join(f"[{d}] {r}" for d, r in ds),
            }
        )
        for who, ds in by_entity.items()
    ] + script_level
    return {
        "desks_incomplete": [_pretty(d) for d in record.get("desks_incomplete") or []],
        "unexamined": [
            f"{u.get('surface', '')} ({', '.join(u.get('scene_ids') or [])})"
            for u in record.get("unexamined") or []
        ],
        "cleared": recorded
        + [{"desk": _pretty(d), "text": q} for d, q in oq_all if _is_determination(q)],
        "open_questions": [
            {"desk": _pretty(d), "text": q} for d, q in oq_all if not _is_determination(q)
        ],
        "rejected": [
            {
                "finding": f.get("flag_id", ""),
                "category": _label(f),
                "reason": _clip(str(f.get("rejection_reason") or ""), 400),
            }
            for f in record.get("rejected_flags", [])
        ],
        "adjudication": [_clip(str(n), 500) for n in record.get("adjudication_notes", [])],
        "rating": (
            {"predicted": pred.get("predicted", ""), "target": pred.get("target", "")}
            if pred.get("predicted")
            else {}
        ),
        "sources": sorted(hosts),
    }


_UNEX_SHOWN = 4


def _not_examined_row(base: dict[str, str], names: list[str]) -> dict[str, str]:
    shown = ", ".join(names[:_UNEX_SHOWN]) + (
        f" (+{len(names) - _UNEX_SHOWN} more)" if len(names) > _UNEX_SHOWN else ""
    )
    return {
        **base,
        "Item": shown,
        "Category": "—",
        "Severity": "",
        "Clearance status": f"NOT EXAMINED — {len(names)} item(s)",
        "Remedy / licensing note": "No desk dispositioned these items; "
        "do not treat this scene as cleared. Rerun the analysis.",
        "Est. cost (USD)": "",
        "Sources": "",
        "Finding": "",
    }


def build(  # noqa: PLR0912 - a deliberate sequence of row-emission cases
    record: dict[str, Any], scene_meta: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """The binder as data: header block + one row per finding per scene, with
    explicit no-known-issue rows so the log covers the whole script."""
    scene_meta = scene_meta or record.get("scene_meta") or {}
    entities = {e.get("entity_id"): e.get("surface") for e in record.get("entities", [])}
    numbers = {sid: str(m.get("number") or "") for sid, m in scene_meta.items()}
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

    # Per-scene unexamined accounting: an entity no desk dispositioned must
    # never let its scene read "No known issue" — absence is not cleanliness.
    unexamined_by_scene: dict[str, list[str]] = defaultdict(list)
    for u in record.get("unexamined") or []:
        for usid in u.get("scene_ids") or []:
            if u.get("surface"):
                unexamined_by_scene[usid].append(u["surface"])

    all_sids = sorted(set(scene_meta) | touched, key=_scene_sort_key)
    rows: list[dict[str, str]] = []
    for sid in all_sids:
        meta = scene_meta.get(sid, {})
        base = {
            "Scene": f"Sc. {numbers[sid]}" if numbers.get(sid) else sid,
            "Page": str(meta.get("page", "")),
            "Scene heading": meta.get("heading", ""),
        }
        flags = sorted(
            by_scene.get(sid, []),
            key=lambda f: list(STATUS_BY_SEVERITY).index(f.get("severity", "FYI")),
        )
        unex_here = unexamined_by_scene.get(sid) or []
        if unex_here:
            rows.append(_not_examined_row(base, unex_here))
        if not flags and sid in touched:
            continue  # covered by a finding anchored at an earlier scene
        if not flags:
            if unex_here:
                continue  # the NOT EXAMINED row already speaks for this scene
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
            rows.append(_flag_row(f, base, entities, sid, numbers))

    rep = record.get("report") or {}
    counts: dict[str, int] = {}
    for row in rows:
        sev = row.get("Severity")
        if sev:
            counts[sev] = counts.get(sev, 0) + 1
    top = [
        {
            "finding": r["Finding"],
            "label": (r["Item"] if r["Item"] != "\u2014" else r["Category"]),
            "severity": r["Severity"],
            "cost": r["Est. cost (USD)"],
            "scene": r["Scene"],
        }
        for r in rows
        if r["Severity"] in ("BLOCKER", "HIGH")
    ]
    used_columns = [c for c in COLUMNS if any(str(r.get(c, "")).strip() for r in rows)] or COLUMNS
    return {
        "title": record.get("script_title") or "Untitled",
        "generated_at": (record.get("generated_at") or "")[:10],
        "score": rep.get("greenlight_score"),
        "counts": counts,
        "draft": record.get("draft") or {},
        "top_exposures": top,
        "back_matter": _back_matter(record),
        "est_cost": rep.get("est_clearance_cost_usd"),
        "columns": used_columns,
        "rows": rows,
        "disclaimer": (
            "Prepared by ScriptRisk (scriptrisk.com). Research tool output, not legal advice; "
            "'No known issue' means no finding survived independent verification, not a legal "
            "clearance. 'NOT EXAMINED' rows mark items no desk dispositioned — those scenes "
            "are not cleared; rerun before relying on this log. Every flagged row cites "
            "public sources available in the full report."
        ),
    }


def to_csv(binder: dict[str, Any]) -> str:
    buf = io.StringIO()
    cols = binder.get("columns") or COLUMNS
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    buf.write(f"# {binder['title']} — Clearance Log — generated {binder['generated_at']}\n")
    buf.write(f"# {binder['disclaimer']}\n")
    w.writeheader()
    for row in binder["rows"]:
        w.writerow(row)
    return buf.getvalue()

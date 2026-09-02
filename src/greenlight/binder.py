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
import re as _re
from collections import defaultdict
from typing import Any

_SCENE_REF_RE = _re.compile(r"\bS\d{3}\b")

STATUS_BY_SEVERITY = {
    "BLOCKER": "DO NOT SHOOT AS WRITTEN — clearance/mitigation required",
    "HIGH": "License / mitigation required",
    "MEDIUM": "Review required",
    "LOW": "Note for file",
    "FYI": "Note for file",
}

_SEV_RANK = {sev: i for i, sev in enumerate(STATUS_BY_SEVERITY)}

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


_DESK_NAMES = {
    "clearance_counsel": "Clearance Counsel",
    "ratings_board": "Ratings Board",
    "safety_underwriter": "Safety Underwriter",
    "territory_censor": "Territory Censor",
}


def _pretty(slug: str) -> str:
    """Desk slugs get their proper names (mirrors common.js deskName) — the
    binder must not call the same desk 'Clearance counsel' that the report
    calls 'Clearance Counsel'."""
    return _DESK_NAMES.get(slug, (slug or "").replace("_", " ").strip().capitalize())


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


def _compact_scene_ref(sids: list[str]) -> str:
    """S003, S004, S005 -> "S003-S005". Range-compressed and NEVER truncated:
    "+2 more" once hid S037 entirely — a scene the log claims to account for
    must be findable by searching its id. Range compression is what keeps the
    PDF scannable; there is no cap (a cap is a truncation with a label)."""
    nums = []
    for s in sids:
        try:
            nums.append(int(s.lstrip("S")))
        except ValueError:
            return ", ".join(sids)
    return ", ".join(_ranges(sorted(nums)))


def _label_ranges(labels: list[str]) -> str:
    """Script-numbered labels ("1", "2", "3", "9") -> "1-3, 9". Non-numeric
    labels ("12A") fall back to the full comma list — every label prints."""
    nums: list[int] = []
    for lab in labels:
        if not lab.isdigit():
            return ", ".join(labels)
        nums.append(int(lab))
    chunks: list[str] = []
    start = prev = nums[0]
    for n in [*sorted(nums)[1:], None]:
        if n is not None and n == prev + 1:
            prev = n
            continue
        chunks.append(str(start) if start == prev else f"{start}-{prev}")
        if n is not None:
            start = prev = n
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
        if seg:
            host = _tier_label(seg[0])
        elif c.get("source_type") == "rules_table":
            # our derived corpus — labeled as a self-citation, never rendered as
            # if it were an external host beside filmratings.com
            host = "ScriptRisk corpus (own aggregate)"
        else:
            host = ""
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def _scene_ref(sids: list[str], numbers: dict[str, str]) -> str:
    """Prefer the script's own locked numbers — the coordinate system every
    production department shares. Generated S### ids compact into ranges."""
    if sids and all(numbers.get(sid) for sid in sids):
        labels = list(dict.fromkeys(numbers[sid] for sid in sids))
        # never "+N more": the 08-30 review's truncation class, on the very
        # surface whose premise is that every scene is findable by its number
        return f"Sc. {_label_ranges(labels)}"
    return _compact_scene_ref(sids)


UNVERIFIED_STATUS = {
    # fail-open findings print on paper too: the counsel-facing artifact must
    # never list an unverified BLOCKER as "DO NOT SHOOT AS WRITTEN" bare
    "blocked": "UNVERIFIED (blocked by the platform content filter)",
    "unavailable": "UNVERIFIED (verifier unavailable)",
}


def _verification_marker(f: dict[str, Any]) -> str:
    if not f.get("verification_unavailable"):
        return ""
    return UNVERIFIED_STATUS["blocked" if f.get("verification_blocked") else "unavailable"]


def _flag_row(
    f: dict[str, Any],
    base: dict[str, str],
    entities: dict[str, Any],
    sid: str,
    numbers: dict[str, str],
) -> dict[str, str]:
    item = _unescape(entities.get(f.get("entity_id")) or "")
    status = STATUS_BY_SEVERITY.get(f.get("severity", ""), "Review")
    marker = _verification_marker(f)
    if marker:
        status = f"{marker} — {status}"
    note = _note(f)
    for q in f.get("_followups") or []:
        # an open question the desk raised ABOUT this finding travels with it —
        # rendered as its follow-up, never as a second item in Open questions
        note = _clip(f"{note}\nOpen point on this finding: {q}", NOTE_CEILING)
    return {
        **base,
        "Scene": _scene_ref(f.get("_all_scenes") or [sid], numbers),
        "Item": item or "\u2014",
        "Category": _label(f),
        "Severity": f.get("severity", ""),
        "Clearance status": status,
        "Remedy / licensing note": note,
        "Est. cost (USD)": _cost_label((f.get("remedy") or {}).get("est_cost_usd") or []),
        "Sources": "\n".join(_hosts(f)[:4]),
        "Finding": f.get("flag_id", ""),
    }


_NO_ISSUE_RE = _re.compile(
    r"\b(?:no (?:known |real[- ]world )?(?:issue|conflict|risk|match|action)"
    r"|negative check|clear(?:ed|ance)?)\b",
    _re.IGNORECASE,
)


def _fold_to_canonical(fold: dict[str, str], eid: Any) -> Any:
    """Follow a fold chain to its fixpoint (E1 -> E2 -> E3), bounded — a
    single hop dropped E1's clearance when E2 was itself a fragment."""
    seen: set[Any] = set()
    while eid in fold and eid not in seen:
        seen.add(eid)
        eid = fold[eid]
    return eid


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


def _back_matter(record: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR0912 - accounting cases
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
    # An entity carrying a surviving FINDING is not "no action needed" — its
    # cleared determinations move to a note, or 78 researched == 78 cleared
    # reads as an accounting impossibility next to 30 findings (run-4 review).
    acct = record.get("entity_accounting") or {}
    fold = acct.get("fold") or {}
    # a flag filed on a short-form id claims the canonical entity as well
    flagged_ids = {
        _fold_to_canonical(fold, f.get("entity_id"))
        for f in record.get("flags", [])
        if f.get("entity_id")
    }
    kept_flag_ids = {f.get("flag_id") for f in record.get("flags", []) if f.get("flag_id")}
    # compounds/truncations counted as folded must not print in cleared, or the
    # header's "N folded" contradicts the list (parity with the web renderer)
    fragment_ids = set(acct.get("fragment_ids") or [])
    # run-13 item 1a (web parity): a finding that names an entity in its BODY
    # also claims it — a "no issue" row beside it is a contradiction. Only
    # no-issue-shaped rows suppress; other facts about the entity stand.
    body_flagged = set(acct.get("body_flagged_ids") or [])
    by_entity: dict[str, list[tuple[str, str]]] = {}
    script_level: list[dict[str, Any]] = []
    flagged_elsewhere = 0
    for d, items in (record.get("cleared") or {}).items():
        for c in items:
            # a short-form's clearance belongs to its canonical entity
            eid = _fold_to_canonical(fold, c.get("entity_id"))
            # still a fragment after folding -> a compound/truncation, drop it;
            # a short-form has folded to a real canonical and is kept there
            if eid in fragment_ids:
                continue
            if eid in flagged_ids:
                flagged_elsewhere += 1
                continue
            if eid in body_flagged and _NO_ISSUE_RE.search(c.get("reasoning") or ""):
                flagged_elsewhere += 1
                continue
            # A determination whose own reasoning cites a surviving finding is
            # a cross-reference, not a clearance — "dispositioned in F2001"
            # must never print under "no action needed" beside the HIGH flag
            # it points at (THE NIGHT COUNTER profanity row; web parity).
            cited = set(_re.findall(r"\bF\d{3,4}\b", c.get("reasoning", "")))
            if cited & kept_flag_ids:
                flagged_elsewhere += 1
                continue
            who = _unescape(ents.get(eid) or ents.get(c.get("entity_id")) or "")
            reasoning = c.get("reasoning", "")
            if who:
                by_entity.setdefault(who, []).append((_pretty(d), reasoning))
            else:
                script_level.append({"desk": _pretty(d), "text": reasoning})
    # one determination per (entity, desk): folded fragments carried near-
    # duplicate reasonings that rendered twice joined by "·" — keep the longest
    for who, ds in by_entity.items():
        best: dict[str, str] = {}
        for desk, reasoning in ds:
            if len(reasoning) > len(best.get(desk, "")):
                best[desk] = reasoning
        by_entity[who] = list(best.items())
    if flagged_elsewhere:
        script_level.append(
            {
                "desk": "note",
                "text": f"{flagged_elsewhere} further determination(s) concern entities "
                "that carry findings — see the findings table, not this list.",
            }
        )
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
                # the one field whose job is explaining a rejection is never
                # ellipsized (run 13: F1006's reason cut mid-clause at 400); the
                # high bound only guards a pathological blob, not a sentence
                "reason": _clip(str(f.get("rejection_reason") or ""), 2000),
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


def _prose_scenes(f: dict[str, Any]) -> list[str]:
    """Every S### the finding's body or remedy names."""
    body = f"{f.get('finding') or ''} {(f.get('remedy') or {}).get('detail') or ''}"
    return _SCENE_REF_RE.findall(body)


def _argued_scene(f: dict[str, Any], sids: list[str]) -> str:
    """The scene the finding's own text argues from, when it names one of its
    anchors; the first anchor otherwise. Deterministic: among body-named anchors
    it takes the LOWEST by scene order, not the first mentioned in prose — two
    findings with the same anchors must land on the same row."""
    named = sorted((s for s in _prose_scenes(f) if s in sids), key=_scene_sort_key)
    return named[0] if named else sids[0]


def build(  # noqa: PLR0912 - a deliberate sequence of row-emission cases
    record: dict[str, Any], scene_meta: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """The binder as data: header block + one row per finding per scene, with
    explicit no-known-issue rows so the log covers the whole script."""
    scene_meta = scene_meta or record.get("scene_meta") or {}
    entities = {e.get("entity_id"): e.get("surface") for e in record.get("entities", [])}
    numbers = {sid: str(m.get("number") or "") for sid, m in scene_meta.items()}
    # One line item per finding, anchored at the scene its body ARGUES from —
    # not the lowest scene number (run-4: five findings displayed "EXT. THE 10
    # FREEWAY" and the Crazy Horse item anchored to the Dean Martin suite).
    # Repeating a finding per scene reads as duplicate exposure and
    # artificially inflates the log.
    known_sids = set(scene_meta)
    by_scene: dict[str, list[dict[str, Any]]] = defaultdict(list)
    touched: set[str] = set()
    covered_by: dict[str, list[str]] = defaultdict(list)  # sid -> flag ids naming it
    followups = record.get("oq_followups") or {}
    for raw in record.get("flags", []):
        if not raw.get("citations"):
            continue  # the invariant, applied here too: uncited findings do not exist
        f = {**raw, "_followups": list(followups.get(raw.get("flag_id"), []) or [])}
        sids = sorted(f.get("scene_ids") or ["(script-wide)"], key=_scene_sort_key)
        touched.update(sids)
        for s in sids:
            covered_by[s].append(f["flag_id"])
        # A scene a finding NAMES IN ITS PROSE must not also render "No known
        # issue": F3006's body called S069 a heat-exposure scene while S069 got
        # its own clean row — the report contradicting itself. The finding's
        # own scene_ids are unchanged (they drive anchoring/coverage); this only
        # stops a prose-named scene from reading clean.
        touched.update(s for s in _prose_scenes(f) if s in known_sids)
        by_scene[_argued_scene(f, sids)].append({**f, "_all_scenes": sids})

    # Per-scene unexamined accounting: an entity no desk dispositioned must
    # never let its scene read "No known issue" — absence is not cleanliness.
    unexamined_by_scene: dict[str, list[str]] = defaultdict(list)
    for u in record.get("unexamined") or []:
        for usid in u.get("scene_ids") or []:
            if u.get("surface"):
                unexamined_by_scene[usid].append(u["surface"])

    rejected_scenes = {
        sid for f in record.get("rejected_flags") or [] for sid in f.get("scene_ids") or []
    }
    all_sids = sorted(set(scene_meta) | touched, key=_scene_sort_key)
    rows: list[dict[str, str]] = []
    for sid in all_sids:
        meta = scene_meta.get(sid, {})
        base = {
            "Scene": f"Sc. {numbers[sid]}" if numbers.get(sid) else sid,
            "Page": str(meta.get("page", "")),
            "Scene heading": meta.get("heading", ""),
            # the scene this row was emitted FOR — what the coverage check counts
            "_scene_id": sid,
        }
        flags = sorted(
            by_scene.get(sid, []),
            key=lambda f: _SEV_RANK.get(f.get("severity", "FYI"), len(_SEV_RANK)),
        )
        unex_here = unexamined_by_scene.get(sid) or []
        if unex_here:
            rows.append(_not_examined_row(base, unex_here))
        if not flags and sid in touched:
            # run-13 item 6d: a silent skip here is how S050 vanished from a log
            # whose premise is scene-by-scene coverage. Every scene emits a row;
            # this one cross-references the finding(s) that cover it.
            refs = ", ".join(dict.fromkeys(covered_by.get(sid, []))) or "a finding"
            rows.append(
                {
                    **base,
                    "Item": "—",
                    "Category": "—",
                    "Severity": "",
                    "Clearance status": f"Covered by {refs} — anchored at another scene",
                    "Remedy / licensing note": "",
                    "Est. cost (USD)": "",
                    "Sources": "",
                    "Finding": "",
                }
            )
            continue
        if not flags:
            if unex_here:
                continue  # the NOT EXAMINED row already speaks for this scene
            if sid in rejected_scenes:
                # a rejected finding covered this scene; rejection is not
                # clearance — "No known issue" here retired a 110mph missing-
                # door drive in run 5
                rows.append(
                    {
                        **base,
                        "Item": "—",
                        "Category": "—",
                        "Severity": "",
                        "Clearance status": "Finding rejected in verification — "
                        "not affirmatively cleared (see Rejected / Open questions)",
                        "Remedy / licensing note": "",
                        "Est. cost (USD)": "",
                        "Sources": "",
                        "Finding": "",
                    }
                )
                continue
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
            "unverified": r["Clearance status"].startswith("UNVERIFIED"),
        }
        for r in rows
        if r["Severity"] in ("BLOCKER", "HIGH")
    ]
    used_columns = [c for c in COLUMNS if any(str(r.get(c, "")).strip() for r in rows)] or COLUMNS
    # run-13 item 6d: the eval asserts rows == scenes, derived not literal —
    # a log that silently omits a scene contradicts its scene-by-scene premise
    return _assemble(record, rep, scene_meta, rows, counts, top, used_columns)


def _assemble(
    record: dict[str, Any],
    rep: dict[str, Any],
    scene_meta: dict[str, dict[str, Any]],
    rows: list[dict[str, str]],
    counts: dict[str, int],
    top: list[dict[str, Any]],
    used_columns: list[str],
) -> dict[str, Any]:
    known_sids = set(scene_meta)
    # ...counted from the BUILT rows, not from the inputs the rows were built
    # from — computed from inputs, the assertion could never fail
    scene_coverage = {
        "scenes": len(scene_meta),
        "scenes_with_rows": len({r["_scene_id"] for r in rows if r.get("_scene_id") in known_sids}),
    }
    unverified = sum(
        1 for r in rows if r["Finding"] and r["Clearance status"].startswith("UNVERIFIED")
    )
    disclaimer = (
        "Prepared by ScriptRisk (scriptrisk.com). Research tool output, not legal advice; "
        "'[partially supported]' marks a finding that survived blinded verification with "
        "caveats — a citation-confidence marker; severity remains the desk's risk "
        "judgment. "
        "'No known issue' means no finding survived independent verification, not a legal "
        "clearance. 'NOT EXAMINED' rows mark items no desk dispositioned — those scenes "
        "are not cleared; rerun before relying on this log. Every flagged row cites "
        "public sources available in the full report."
    )
    if unverified:
        disclaimer += (
            f" {unverified} row(s) marked UNVERIFIED survived fail-open because the independent "
            "verifier could not run on them — they are desk claims, not verified findings, "
            "and are excluded from the score and cost totals."
        )
    return {
        "scene_coverage": scene_coverage,
        "title": _one_line(record.get("script_title") or "Untitled"),
        "generated_at": (record.get("generated_at") or "")[:10],
        "score": rep.get("greenlight_score"),
        # WHY a score is withheld travels with it — the PDFs said "analysis
        # incomplete" for a verifier outage too
        "verification_degraded": bool(rep.get("verification_degraded")),
        "unverified_rows": unverified,
        "counts": counts,
        "draft": record.get("draft") or {},
        "top_exposures": top,
        "back_matter": _back_matter(record),
        "est_cost": rep.get("est_clearance_cost_usd"),
        # two-path totals render on EVERY surface that prints a total, or the
        # binder headlines a number the web report says the production avoids
        "est_cost_paths": rep.get("est_cost_paths") or None,
        "columns": used_columns,
        "rows": rows,
        "disclaimer": disclaimer,
    }


def _one_line(text: str) -> str:
    """A title with a newline in it would inject a row into the CSV's comment
    header; collapse all whitespace runs to one space."""
    return " ".join(str(text).split())


def to_csv(binder: dict[str, Any]) -> str:
    buf = io.StringIO()
    cols = binder.get("columns") or COLUMNS
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    buf.write(
        f"# {_one_line(binder['title'])} — Clearance Log — generated {binder['generated_at']}\n"
    )
    buf.write(f"# {_one_line(binder['disclaimer'])}\n")
    w.writeheader()
    for row in binder["rows"]:
        w.writerow(row)
    return buf.getvalue()

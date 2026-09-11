"""Revision-aware rescan, stage 1: the findings diff.

A clearance report is only valid for the exact draft it ran against; a new
draft gets a full re-run, and this module answers the question the producer
actually has: WHAT CHANGED. Findings are matched across the two runs with
the same surface-based matcher the consistency measurements use (entity ids
are per-run positional and useless across runs). Deterministic, offline.

Stage 2 (re-analyzing only asterisked pages from FDX revision marks) builds
on this; the diff is the product either way.
"""

from __future__ import annotations

from typing import Any

from greenlight.consistency import match_runs

_SUMMARY_FIELDS = ("flag_id", "category", "severity", "finding", "scene_ids")


def _slim(flag: dict[str, Any]) -> dict[str, Any]:
    out = {k: flag.get(k) for k in _SUMMARY_FIELDS}
    out["finding"] = str(out.get("finding") or "")[:280]
    return out


def diff_records(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Compare findings without treating disappearance as clearance.

    `not_reproduced` holds prior findings absent from the new analysis, even
    when the draft changed: an edit alone does not establish a remedy. Keep
    the legacy `resolved` list empty until an evidence-backed resolution
    workflow exists. Both identical-text reruns and partial runs can miss a
    previously filed issue.
    """
    match = match_runs([old, new])
    old_flags = {f["flag_id"]: f for f in old.get("flags", [])}
    new_flags = {f["flag_id"]: f for f in new.get("flags", [])}

    added, not_reproduced, unchanged, severity_changed = [], [], [], []
    for g in match["groups"]:
        in_old, in_new = g["runs"][0], g["runs"][1]
        ids = {fid.split(":", 1)[0]: fid.split(":", 1)[1] for fid in g["flag_ids"]}
        of = old_flags.get(ids.get("run1", ""))
        nf = new_flags.get(ids.get("run2", ""))
        if in_new and not in_old and nf:
            added.append(_slim(nf))
        elif in_old and not in_new and of:
            not_reproduced.append(_slim(of))
        elif of and nf:
            if of.get("severity") != nf.get("severity"):
                severity_changed.append({**_slim(nf), "was_severity": of.get("severity")})
            else:
                unchanged.append(_slim(nf))

    old_draft, new_draft = old.get("draft") or {}, new.get("draft") or {}
    return {
        "new": added,
        "resolved": [],
        "not_reproduced": not_reproduced,
        "unchanged": unchanged,
        "severity_changed": severity_changed,
        "fuzzy_merges": match["fuzzy_merges"],
        "drafts": {
            "previous": {k: old_draft.get(k) for k in ("sha256", "pages", "scene_count")},
            "current": {k: new_draft.get(k) for k in ("sha256", "pages", "scene_count")},
            "same_text": bool(old_draft.get("sha256"))
            and old_draft.get("sha256") == new_draft.get("sha256"),
        },
        "summary": (
            f"{len(added)} new, {len(not_reproduced)} not reproduced, "
            f"{len(unchanged)} unchanged, {len(severity_changed)} severity changes"
        ),
    }

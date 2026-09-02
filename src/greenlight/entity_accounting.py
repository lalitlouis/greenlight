"""Distinct-entity accounting for report headlines.

Triage extracts surfaces as they appear on the page, so the raw list carries
fragments and duplicates — "Vick" plus "Vick and Alan", "Doug" and "Doug
Billings", a truncated "& Forever Wedding" next to "& Forever Wedding Chapel".
Labeling them pre-pass candidates is honest, but they must not inflate the
headline ("78 entities researched", run-4 review). Deterministic, display-only:
worklists and desk accounting keep the raw list.
"""

from __future__ import annotations

import re
from typing import Any

_TRUNCATION_PREFIXES = ("& ", "and ", "or ", ", ", "- ", "— ")

# run-13 item 6a: PDF extraction artifacts ("I (cid:60) ROGER") rendered as
# entity NAMES four runs running. Display strip only — raw worklists and
# matching keep the raw surface.
_CID_RE = re.compile(r"\s*\(cid:\d+\)\s*")

# run-13 item 1b: a cleared determination may not assert a completed search
# nothing backs. The claim shapes, pinned:
_WORK_CLAIM_RE = re.compile(
    r"negative check confirmed|confirmed no real[- ]world|search(?:es)? confirm(?:s|ed)? no"
    r"|verified (?:that )?no",
    re.IGNORECASE,
)
# run-13 item 1a: suppression targets CONTRADICTION — a no-issue-shaped row
# beside a finding about the same subject. A determination recording some other
# fact about the entity stands.
_NO_ISSUE_RE = re.compile(
    r"\b(?:no (?:known |real[- ]world )?(?:issue|conflict|risk|match|action)"
    r"|negative check|clear(?:ed|ance)?)\b",
    re.IGNORECASE,
)
_MIN_SUPPRESS_SURFACE = 4  # a 'Doug' substring inside a word must never suppress


def strip_cid(surface: str) -> str:
    return " ".join(_CID_RE.sub(" ", surface or "").split())


def polish_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Display-only assembly transforms (run-13 items 1 + 6a). Mutates the
    record; returns guard-manifest entries. Deterministic; desk state and raw
    worklists untouched.

    1. (cid:NN) stripped from rendered entity surfaces.
    2. body_flagged_ids: entities a kept flag names in its FINDING BODY (never
       the remedy — 'negotiate with MGM management' names a counterparty, not a
       subject). The renderer suppresses their no-issue determinations into the
       'counted there, not here' note, exactly like slot-referenced entities.
    3. A work-performed claim ('negative check confirmed') with NO research
       receipt is rewritten to what the record supports. Receipts count batch
       sweeps: a per-entity research key OR any research entry whose
       objective/query text names the surface — without that arm, every entity
       a real sweep covered would have its TRUE determination destroyed.
    """
    entries: list[dict[str, Any]] = []
    for e in record.get("entities") or []:
        cleaned = strip_cid(str(e.get("surface") or ""))
        if cleaned and cleaned != e.get("surface"):
            e["surface"] = cleaned
    for u in record.get("unexamined") or []:
        cleaned = strip_cid(str(u.get("surface") or ""))
        if cleaned and cleaned != u.get("surface"):
            u["surface"] = cleaned

    surf_by_id = {
        str(e.get("entity_id") or ""): str(e.get("surface") or "")
        for e in record.get("entities") or []
        if e.get("entity_id")
    }
    bodies = "\n".join(str(f.get("finding") or "") for f in record.get("flags") or []).lower()
    body_flagged = sorted(
        eid
        for eid, s in surf_by_id.items()
        if len(s) >= _MIN_SUPPRESS_SURFACE and re.search(rf"\b{re.escape(s.lower())}\b", bodies)
    )
    acct = record.get("entity_accounting")
    fold = (acct or {}).get("fold") or {} if isinstance(acct, dict) else {}
    # canonicalise through the fold: a finding that names the short form claims
    # the canonical entity too (B14) — and expose the canonical flagged set so
    # every renderer tests the same ids instead of re-deriving them
    body_flagged = sorted({*body_flagged, *(fold.get(e, e) for e in body_flagged)})
    flagged_ids = sorted(
        {
            fold.get(eid, eid)
            for f in record.get("flags") or []
            if (eid := str(f.get("entity_id") or ""))
        }
    )
    if isinstance(acct, dict):
        acct["body_flagged_ids"] = body_flagged
        acct["flagged_ids"] = flagged_ids

    research = record.get("research") or {}

    def _has_receipt(eid: str, surface: str) -> bool:
        if eid and any(k.startswith(f"research:{eid}:") for k in research):
            return True
        low = surface.lower()
        if len(low) < _MIN_SUPPRESS_SURFACE:
            return False
        return any(
            low in str(v.get("objective") or "").lower()
            or low in str(v.get("queries") or "").lower()
            for v in research.values()
            if isinstance(v, dict)
        )

    flag_by_surface = {}
    for f in record.get("flags") or []:
        body = str(f.get("finding") or "").lower()
        for eid, s in surf_by_id.items():
            if len(s) >= _MIN_SUPPRESS_SURFACE and re.search(rf"\b{re.escape(s.lower())}\b", body):
                flag_by_surface.setdefault(eid, f.get("flag_id"))

    for _desk, items in (record.get("cleared") or {}).items():
        for c in items or []:
            txt = str(c.get("reasoning") or "")
            if not _WORK_CLAIM_RE.search(txt):
                continue
            eid = str(c.get("entity_id") or "")
            surface = surf_by_id.get(eid, "")
            if _has_receipt(eid, surface):
                continue  # the claim is true — never weaken honest work
            ref = flag_by_surface.get(eid)
            c["reasoning"] = (
                "No research trace supports this determination — treat it as unverified; "
                "a name-commonality sweep is recommended" + (f" — see {ref}." if ref else ".")
            )
            c["rephrased"] = True
            entries.append(
                {
                    "guard": "cleared_rephrase",
                    "stage": "assembly",
                    "entity": eid or surface,
                    "matched": txt[:120],
                }
            )
    return entries


def _is_truncation(surface: str) -> bool:
    t = surface.strip().lower()
    return not t or t in ("&", "and", "or") or t.startswith(_TRUNCATION_PREFIXES)


def account(entities: list[dict[str, Any]]) -> dict[str, Any]:
    """{"researched", "distinct", "fragments", "fold"}. `fold` maps a folded
    short-form's entity_id to its canonical entity_id ("Doug" -> "Doug
    Billings"), so display surfaces can merge their cleared determinations
    instead of rendering the same entity twice (run 5: 97 determinations
    across 72 items, folded fragments each rendering their reasoning twice)."""
    surfaces = [str(e.get("surface") or "").strip() for e in entities]
    ids = [str(e.get("entity_id") or "") for e in entities]
    n = len(surfaces)
    low = [s.lower() for s in surfaces]
    # A truncation artifact begins with a dangling connective ("& Forever Wedding").
    # NOT "starts with a non-letter" — that wrongly folded real entities away
    # ("1967 Cadillac Deville", ".357 MAGNUM"), shrinking the headline count.
    frag = [_is_truncation(s) for s in surfaces]

    # Compounds ("Stu and Vick", "X & Y") whose component also stands alone are
    # groupings of existing entities, not entities.
    standalone = set(low)
    for i, s in enumerate(low):
        if frag[i]:
            continue
        parts = re.split(r"\s+(?:and|&)\s+", s)
        if len(parts) > 1 and any(p in standalone for p in parts):
            frag[i] = True

    # A single-token surface contained on a word boundary in a longer,
    # non-fragment surface is the same entity's short form ("Doug" ⊂ "Doug
    # Billings") — count it once, under the longer form.
    fold: dict[str, str] = {}
    for i, s in enumerate(low):
        if frag[i] or not s or " " in s:
            continue
        pat = re.compile(rf"\b{re.escape(s)}\b")
        host = next(
            (
                j
                for j, t in enumerate(low)
                if i != j and not frag[j] and len(t) > len(s) and pat.search(t)
            ),
            None,
        )
        if host is not None:
            frag[i] = True
            if ids[i] and ids[host]:
                fold[ids[i]] = ids[host]

    # Chains fold to a FIXPOINT: "Bob" -> "Bob's" -> "Bob's Burgers" must land
    # on the canonical entity, not on an intermediate the renderers then drop
    # as a fragment (review 2026-09-01 B14: single-hop folding lost E1's
    # clearance entirely). Cycle-guarded; deterministic.
    for src in list(fold):
        seen = {src}
        dst = fold[src]
        while dst in fold and dst not in seen:
            seen.add(dst)
            dst = fold[dst]
        fold[src] = dst

    distinct = sum(1 for x in frag if not x)
    # every folded/fragment id, so the cleared list can DROP them and reconcile
    # with the headline: "distinct" entities and shown determinations must agree.
    # (Header claimed "14 folded" while 10 compounds still printed in cleared.)
    fragment_ids = [ids[i] for i in range(n) if frag[i] and ids[i]]
    return {
        "researched": n,
        "distinct": distinct,
        "fragments": n - distinct,
        "fold": fold,
        "fragment_ids": fragment_ids,
    }


# The web's isDetermination(), ported verbatim (report.js): an open question
# shaped like a clearance counts as a script-level cleared row, not an unknown.
_OQ_QUESTION_RE = re.compile(r"\?\s*$")
_OQ_UNRESOLVED_RE = re.compile(
    r"\b(unclear|unresolved|unknown|unable|could(?:n't| not)|pending|unverified"
    r"|needs? (?:further|manual)|open question)\b",
    re.IGNORECASE,
)
_OQ_DETERMINATION_RE = re.compile(
    r"\bno (?:synchronization|sync|master(?:[- ]use)?|licen[cs]e|clearance|release|permit"
    r"|action)\b[^.?]*\b(?:required|needed|necessary)\b",
    re.IGNORECASE,
)


def is_determination(text: Any) -> bool:
    t = str(text)
    if _OQ_QUESTION_RE.search(t) or _OQ_UNRESOLVED_RE.search(t):
        return False
    return bool(re.search(r"\bcleared\b", t, re.IGNORECASE)) or bool(_OQ_DETERMINATION_RE.search(t))


def items_examined(record: dict[str, Any]) -> dict[str, int]:
    """The decomposition behind "N items examined" (review B13): the web's
    clearedRows() row count is distinct cleared ENTITIES plus SCRIPT-LEVEL
    determinations (territory axis sweeps, desk-wide clearances, determination-
    shaped open questions). Computed here, once, so every surface can print
    "31 entities + 16 script-wide checks" and a reader can reconcile it against
    "39 entities researched". Mirrors report.js clearedRows exactly, keyed on
    KEPT flag ids (a determination citing a rendered finding is counted there,
    not here)."""
    acct = record.get("entity_accounting") or {}
    fold = acct.get("fold") or {}
    fragment_ids = set(acct.get("fragment_ids") or [])
    body_flagged = set(acct.get("body_flagged_ids") or [])
    flags = record.get("flags") or []
    kept_ids = {f.get("flag_id") for f in flags if f.get("flag_id")}
    flagged_ids = set(acct.get("flagged_ids") or []) | {
        fold.get(eid, eid) for f in flags if (eid := str(f.get("entity_id") or ""))
    }
    surf_by_id = {
        str(e.get("entity_id") or ""): str(e.get("surface") or "")
        for e in record.get("entities") or []
        if e.get("entity_id")
    }
    entity_rows: set[str] = set()
    script_level = 0
    flagged_elsewhere = 0
    for _desk, items in (record.get("cleared") or {}).items():
        for c in items or []:
            raw = str(c.get("entity_id") or "")
            eid = fold.get(raw, raw)
            if eid in fragment_ids:
                continue
            reasoning = str(c.get("reasoning") or "")
            if eid and (
                eid in flagged_ids or (eid in body_flagged and _NO_ISSUE_RE.search(reasoning))
            ):
                flagged_elsewhere += 1
                continue
            if any(fid in kept_ids for fid in re.findall(r"\bF\d{3,4}\b", reasoning)):
                flagged_elsewhere += 1
                continue
            who = surf_by_id.get(eid) or surf_by_id.get(raw)
            if who:
                entity_rows.add(who)
            else:
                script_level += 1
    for _desk, qs in (record.get("open_questions") or {}).items():
        script_level += sum(1 for q in qs or [] if is_determination(q))
    return {
        "entity_rows": len(entity_rows),
        "script_level": script_level,
        "flagged_elsewhere": flagged_elsewhere,
    }

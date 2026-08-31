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

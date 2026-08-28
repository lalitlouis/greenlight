"""k-run self-consistency: the matcher, the agreement math, the recall bound.

Pure functions over run records — the k-run driver lives in
scripts/consistency_k3.py; everything here is offline-testable.

Design note (differs from the Wave-2 memo): entity_id is POSITIONAL per
triage pass — E014 in one run is a different person in the next. The
canonical cross-run key is the normalized entity SURFACE + category, with
fuzzy surface matching as the primary mechanism and the fuzzy-miss rate
reported as an entity-resolution quality metric in its own right.
"""

from __future__ import annotations

import difflib
import re
from collections import defaultdict
from typing import Any

_FUZZY_THRESHOLD = 0.8
_TOKEN_JACCARD = 0.75  # a wholly different token (Cameron vs Tyler) is a different entity
_NEAR_MISS_FLOOR = 0.55  # unmerged pairs above this get logged for hand review
_MIN_RATERS = 2  # a row needs two observations to say anything about agreement


def _fuzzy_same(a: str, b: str) -> bool:
    """Punctuation/spelling drift merges; a distinct token does not.
    Containment also merges: "nighthawks" and "edward hopper s nighthawks"
    are one finding whose surface one desk elaborated — requiring ratio
    alone left both as singletons in the first feature-scale k=3."""
    ta, tb = set(a.split()), set(b.split())
    if ta and tb and (ta <= tb or tb <= ta):
        return True
    if difflib.SequenceMatcher(None, a, b).ratio() < _FUZZY_THRESHOLD:
        return False
    union = ta | tb
    return bool(union) and len(ta & tb) / len(union) >= _TOKEN_JACCARD


_ARTICLES = re.compile(r"\b(the|a|an)\b", re.I)
_JUNK = re.compile(r"[^a-z0-9 ]+")


def normalize_surface(surface: str) -> str:
    s = _ARTICLES.sub(" ", (surface or "").lower())
    s = _JUNK.sub(" ", s)
    return " ".join(s.split())


def finding_key(flag: dict[str, Any], entities: dict[str, str]) -> tuple[str, str]:
    """(normalized surface | scene anchor, category). Stable across runs."""
    surface = entities.get(flag.get("entity_id") or "", "")
    if surface:
        return (normalize_surface(surface), flag.get("category", ""))
    sids = sorted(flag.get("scene_ids") or ["(none)"])
    return (f"@{sids[0]}", flag.get("category", ""))


def match_runs(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Union findings across k run records into canonical groups.

    Returns {groups: [{key, category, label, runs: [bool]*k, flag_ids}],
             fuzzy_merges, unmatched_rate}."""
    per_run_keys: list[dict[tuple[str, str], dict[str, Any]]] = []
    for rec in records:
        ents = {e.get("entity_id"): e.get("surface", "") for e in rec.get("entities", [])}
        keyed: dict[tuple[str, str], dict[str, Any]] = {}
        for f in rec.get("flags", []):
            keyed.setdefault(finding_key(f, ents), f)
        per_run_keys.append(keyed)

    canon: list[tuple[str, str]] = []
    alias: dict[tuple[str, str], tuple[str, str]] = {}
    fuzzy_merges = 0
    near_misses: list[dict[str, Any]] = []

    def resolve(key: tuple[str, str]) -> tuple[str, str]:
        nonlocal fuzzy_merges
        if key in alias:
            return alias[key]
        surface, cat = key
        if not surface.startswith("@"):
            for c_surface, c_cat in canon:
                if c_cat != cat or c_surface.startswith("@"):
                    continue
                if _fuzzy_same(surface, c_surface):
                    alias[key] = (c_surface, c_cat)
                    fuzzy_merges += 1
                    return alias[key]
                ratio = difflib.SequenceMatcher(None, surface, c_surface).ratio()
                if ratio >= _NEAR_MISS_FLOOR:
                    # if this fills with Zuckerberg/Mark Zuckerberg pairs, a low
                    # alpha is a matcher artifact — read this BEFORE alpha
                    near_misses.append(
                        {"a": surface, "b": c_surface, "category": cat, "ratio": round(ratio, 3)}
                    )
        canon.append(key)
        alias[key] = key
        return key

    presence: dict[tuple[str, str], list[bool]] = defaultdict(lambda: [False] * len(records))
    flag_ids: dict[tuple[str, str], list[str]] = defaultdict(list)
    for i, keyed in enumerate(per_run_keys):
        for key, f in keyed.items():
            ckey = resolve(key)
            presence[ckey][i] = True
            flag_ids[ckey].append(f"run{i + 1}:{f.get('flag_id')}")

    groups = [
        {
            "key": "|".join(k),
            "category": k[1],
            "label": k[0],
            "runs": presence[k],
            "agreement": f"{sum(presence[k])}/{len(records)}",
            "flag_ids": flag_ids[k],
        }
        for k in canon
    ]
    total = sum(len(kd) for kd in per_run_keys)
    return {
        "groups": groups,
        "fuzzy_merges": fuzzy_merges,
        "near_misses": near_misses,
        "union_size": len(groups),
        "total_findings": total,
    }


def gwet_ac1_binary(rows: list[list[bool]]) -> float | None:
    """Gwet's AC1 for binary ratings with missing data. Chance-corrected like
    Krippendorff's alpha but stable under high prevalence — alpha degenerates
    toward 0 when nearly all judgments share one value (the feature-scale k=3:
    36/37 unanimous rows, alpha 0.0), which is exactly the regime AC1 was
    designed for. Rows are per-item observation lists; only rows with 2+
    observations contribute.

    AC1 = (Pa - Pe) / (1 - Pe), Pe = 2*pi*(1-pi) with pi the overall
    proportion of positive ratings."""
    rated = [r for r in rows if len(r) >= _MIN_RATERS]
    if not rated:
        return None
    total = sum(len(r) for r in rated)
    pi = sum(sum(r) for r in rated) / total if total else 0.0
    pe = 2.0 * pi * (1.0 - pi)
    pa_num = pa_den = 0.0
    for r in rated:
        n = len(r)
        k = sum(r)
        pa_num += (k * (k - 1) + (n - k) * (n - k - 1)) / (n - 1)
        pa_den += n
    pa = pa_num / pa_den if pa_den else 0.0
    if pe >= 1.0:
        return None
    return (pa - pe) / (1.0 - pe)


def krippendorff_alpha_binary(matrix: list[list[bool | None]]) -> float | None:
    """Krippendorff's alpha for binary nominal data with missing values.
    Rows = items (union of finding groups), columns = runs; None = run missing."""
    pairs_agree = 0.0
    pairs_total = 0.0
    ones = zeros = 0
    for row in matrix:
        vals = [v for v in row if v is not None]
        m = len(vals)
        if m < _MIN_RATERS:
            continue
        one = sum(vals)
        ones += one
        zeros += m - one
        pairs_total += m * (m - 1)
        pairs_agree += one * (one - 1) + (m - one) * (m - one - 1)
    if pairs_total == 0:
        return None
    do = 1.0 - pairs_agree / pairs_total
    n = ones + zeros
    if n < _MIN_RATERS or ones == 0 or zeros == 0:
        return 1.0 if do == 0 else 0.0
    de = (2.0 * ones * zeros) / (n * (n - 1))
    if de == 0:
        return None
    return 1.0 - do / de


def chapman_estimate(n1: int, n2: int, overlap: int) -> float:
    """Chapman estimator of total findable items from two runs' findings."""
    return ((n1 + 1) * (n2 + 1)) / (overlap + 1) - 1


def recall_bound(match: dict[str, Any]) -> dict[str, Any]:
    """Pairwise Chapman across k runs -> recall upper bound for the union.
    Heterogeneous catchability biases N-hat DOWN, so report recall as
    'no better than X' — an upper bound, never a point estimate."""
    groups = match["groups"]
    k = len(groups[0]["runs"]) if groups else 0
    estimates = []
    for i in range(k):
        for j in range(i + 1, k):
            n1 = sum(1 for g in groups if g["runs"][i])
            n2 = sum(1 for g in groups if g["runs"][j])
            m = sum(1 for g in groups if g["runs"][i] and g["runs"][j])
            estimates.append(chapman_estimate(n1, n2, m))
    if not estimates:
        return {}
    n_hat = sum(estimates) / len(estimates)
    union = match["union_size"]
    return {
        "n_hat": round(n_hat, 1),
        "union": union,
        "recall_upper_bound": round(min(1.0, union / n_hat) if n_hat > 0 else 1.0, 3),
        "pairwise_estimates": [round(e, 1) for e in estimates],
    }


def surfaces_by_disposition(rec: dict[str, Any]) -> tuple[set[str], set[str]]:
    """(flagged surfaces, cleared surfaces), normalized — one record."""
    ents = {e.get("entity_id"): e.get("surface", "") for e in rec.get("entities", [])}
    flagged = {
        normalize_surface(ents.get(f.get("entity_id") or "", ""))
        for f in rec.get("flags", [])
        if ents.get(f.get("entity_id") or "")
    }
    cleared = set()
    for items in (rec.get("cleared") or {}).values():
        for c in items:
            surf = ents.get(c.get("entity_id") or "", "")
            if surf:
                cleared.add(normalize_surface(surf))
    return flagged, cleared - flagged


def alpha_with_clearances(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Krippendorff over flag-vs-cleared decisions, entity level.

    The union-of-findings matrix has no agreed negatives, so chance agreement
    ~= observed and alpha collapses toward zero by construction. Explicit
    clearances are the negatives: rows = entities dispositioned anywhere,
    cell = flagged (True) / cleared (False) / not dispositioned (None).
    """
    dispositions = [surfaces_by_disposition(r) for r in records]
    universe = set()
    for flagged, cleared in dispositions:
        universe |= flagged | cleared
    matrix: list[list[bool | None]] = []
    for surf in sorted(universe):
        row: list[bool | None] = []
        for flagged, cleared in dispositions:
            row.append(True if surf in flagged else False if surf in cleared else None)
        matrix.append(row)
    rated_rows = [r for r in matrix if sum(v is not None for v in r) >= _MIN_RATERS]
    unanimous = sum(1 for r in rated_rows if len({v for v in r if v is not None}) == 1)
    total = sum(sum(v is not None for v in r) for r in rated_rows)
    pos = sum(sum(bool(v) for v in r if v is not None) for r in rated_rows)
    return {
        "alpha": krippendorff_alpha_binary(matrix),
        "ac1": gwet_ac1_binary([[bool(v) for v in r if v is not None] for r in rated_rows]),
        "raw_agreement": (unanimous / len(rated_rows)) if rated_rows else None,
        "prevalence_flag": (pos / total) if total else None,
        "universe": len(universe),
        "rows_with_2plus_observations": len(rated_rows),
        "unanimous_rows": unanimous,
    }

#!/usr/bin/env python3
"""Report-integrity invariants shared by BOTH eval gates.

`scripts/eval_run.py` (the fixture gate) and `scripts/eval_scale.py` (the
scale gate) each carry their own seeded ground truth; the invariants below are
script-independent — a report must satisfy them for ANY screenplay — so they
live once, here, and both gates import them. The 2026-09-01 review found the
scale gate had drifted nine invariants behind the fixture gate; a shared module
is how that cannot recur.

Every check is deterministic over the run record (no network). Each returns
(name, ok, detail); the gates print and count them.
"""

from __future__ import annotations

import re
from typing import Any

from greenlight.names import untraceable_rightsholders as _untraceable_names

Check = tuple[str, bool, str]

RATING_RANK = {"G": 0, "PG": 1, "PG-13": 2, "R": 3, "NC-17": 4}
_FID = re.compile(r"\bF\d{3,4}\b")
_SID = re.compile(r"\bS\d{3}\b")
_YEAR = re.compile(r"\b(1[89]\d{2}|2[01]\d{2})\b")
_TERM = re.compile(r"\b(\d{2,3})\s*(?:-|\s)?years?\b", re.IGNORECASE)
# "protected through 2038" must equal base + term exactly; "until / expires /
# enters the public domain in 2038" may be the year AFTER the last protected one
_THROUGH = re.compile(r"\bthrough\s+(?:the end of\s+)?(1[89]\d{2}|2[01]\d{2})\b", re.IGNORECASE)
_UNTIL = re.compile(
    r"\b(?:until|expir\w*(?: in| at the end of| on)?|public domain (?:in|on|from|as of)"
    r"|pd (?:in|from)|from)\s+(?:january 1,? )?(1[89]\d{2}|2[01]\d{2})\b",
    re.IGNORECASE,
)
_UNRESOLVED_TEMPLATE = "Unresolved —"
# the rightsholder extractor is SHARED with the filing gate (greenlight.names) —
# the gate and the assertion cannot drift apart


def expand_scene_label(label: str, number_to_sid: dict[str, str]) -> set[str]:
    """A binder row's Scene label -> the scene ids it accounts for. Labels are
    range-compressed ("S002, S004-S005, S009") or script-numbered ("Sc. 1-3,
    9"); either way every scene the label covers must be recoverable from the
    label alone, or the log's scene-by-scene premise is untestable."""
    out: set[str] = set()
    text = str(label or "").strip()
    numbered = text.startswith("Sc.")
    body = text[3:] if numbered else text
    for tok in [t.strip() for t in body.split(",") if t.strip()]:
        if numbered:
            a, _, b = tok.partition("-")
            if a.isdigit() and (b.isdigit() or not b):
                for n in range(int(a), int(b or a) + 1):
                    sid = number_to_sid.get(str(n))
                    if sid:
                        out.add(sid)
            elif tok in number_to_sid:
                out.add(number_to_sid[tok])
            continue
        m = re.fullmatch(r"S(\d{3})(?:-S(\d{3}))?", tok)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
            out.update(f"S{n:03d}" for n in range(lo, hi + 1))
    return out


def _body(f: dict[str, Any]) -> str:
    return f"{f.get('finding') or ''} {(f.get('remedy') or {}).get('detail') or ''}"


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split())


def term_arithmetic_problems(text: str) -> list[str]:
    """Sentences stating a base year, an N-year term and an expiry year whose
    arithmetic disagrees. Pure; exposed for tests."""
    out: list[str] = []
    for sent in re.split(r"(?<=[.;])\s+", text or ""):
        terms = _TERM.findall(sent)
        if len(terms) != 1:
            continue
        term = int(terms[0])
        years = sorted({int(y) for y in _YEAR.findall(sent)})
        if len(years) < 2:
            continue
        base = years[0]
        for m in _THROUGH.finditer(sent):
            exp = int(m.group(1))
            if exp <= base:
                continue
            if exp != base + term:
                out.append(
                    f"{base} + {term} years is through {base + term}, text says through {exp}"
                )
        for m in _UNTIL.finditer(sent):
            exp = int(m.group(1))
            if exp <= base:
                continue
            if exp not in (base + term, base + term + 1):
                out.append(f"{base} + {term} years ends {base + term}, text says {exp}")
    return out


def untraceable_rightsholders(flag: dict[str, Any]) -> list[str]:
    """Rightsholder-shaped names in a *_license finding whose distinctive tokens
    appear in none of that finding's excerpts. Pure; exposed for tests."""
    excerpts = " ".join(str(c.get("excerpt") or "") for c in flag.get("citations") or [])
    return _untraceable_names(_body(flag), excerpts)


def shared_invariants(  # noqa: PLR0912, PLR0915 - a flat checklist, deliberately linear
    r: dict[str, Any], *, rejection_cap: float = 0.4
) -> list[Check]:
    from greenlight import binder as _binder
    from greenlight.tools.toolbelt import (
        _NORMATIVE_RULE_RE,
        _statute_sections,
        boundary_eval,
        comps_weighted_majority,
    )

    checks: list[Check] = []

    def check(name: str, ok: Any, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    flags = r.get("flags") or []
    rejected = r.get("rejected_flags") or []
    rep = r.get("report") or {}
    kept_ids = {f.get("flag_id") for f in flags}
    rejected_ids = {f.get("flag_id") for f in rejected if f.get("flag_id")}
    withdrawn = set(r.get("withdrawn_flag_ids") or [])
    scene_meta = r.get("scene_meta") if isinstance(r.get("scene_meta"), dict) else {}

    # --- run health
    check(
        "invariant: run completed without error or salvage",
        not r.get("error"),
        f"error={str(r.get('error'))[:80]}",
    )
    all_ids = [f.get("flag_id") for f in [*flags, *rejected]]
    check(
        "invariant: flag ids unique across kept and rejected",
        len(all_ids) == len(set(all_ids)),
        f"{len(all_ids)} ids, {len(set(all_ids))} distinct",
    )
    verdicts = r.get("verdicts") or {}
    verdict_ids = {str(k).split(":")[0] for k in verdicts}
    check(
        f"verification: ran on every kept flag, rejection rate <= {round(rejection_cap * 100)}%",
        bool(verdicts)
        and kept_ids <= verdict_ids
        and not any(f.get("verification_unavailable") for f in flags)
        and len(rejected) <= rejection_cap * max(1, len(rejected) + len(flags)),
        f"{len(rejected)} rejected / {len(rejected) + len(flags)} filed; verdicts for "
        f"{len(verdict_ids)} flags — zero rejections is legitimate when the desks' filing "
        "gates already blocked the weak flags; a sleeping verifier shows as missing "
        "verdicts or fail-open markers, and those fail this check",
    )

    # --- the citation invariant and referential integrity
    check(
        "invariant: every kept flag has a citation with an excerpt",
        all(
            f.get("citations") and all(str(c.get("excerpt") or "").strip() for c in f["citations"])
            for f in flags
        ),
    )
    dangling = [
        n for n in r.get("adjudication_notes") or [] if not set(_FID.findall(n)) <= kept_ids
    ]
    check(
        "invariant: no adjudication note references a non-rendered finding id",
        not dangling,
        f"dangling: {[n[:50] for n in dangling]}",
    )
    allowed = kept_ids | rejected_ids | withdrawn
    bad_refs: list[tuple[str, str]] = []
    for _desk, items in (r.get("cleared") or {}).items():
        for c in items or []:
            for fid in _FID.findall(str((c or {}).get("reasoning") or "")):
                if fid not in allowed:
                    bad_refs.append(("cleared", fid))
    for _desk, qs in (r.get("open_questions") or {}).items():
        for q in qs or []:
            for fid in _FID.findall(str(q)):
                if fid not in allowed:
                    bad_refs.append(("open_question", fid))
    for _fid, qs in (r.get("oq_followups") or {}).items():
        for q in qs or []:
            for fid in _FID.findall(str(q)):
                if fid not in allowed:
                    bad_refs.append(("followup", fid))
    for f in flags:
        for fid in _FID.findall(_body(f)):
            if fid not in allowed:
                bad_refs.append((f.get("flag_id", "?"), fid))
    check(
        "invariant: no cleared/open-question/finding text cites an id that neither renders "
        "nor is rejected",
        not bad_refs,
        f"phantom references: {bad_refs[:6]} — absorbed ids must be rewritten to their "
        "survivor; rejected/withdrawn ids stay, annotated",
    )
    restated: list[tuple[str, str]] = []
    for desk, qs in (r.get("open_questions") or {}).items():
        desk_kept = {f.get("flag_id") for f in flags if f.get("agent") == desk}
        for q in qs or []:
            text = str(q)
            if text.startswith(_UNRESOLVED_TEMPLATE):
                continue
            for fid in set(_FID.findall(text)) & desk_kept:
                restated.append((desk, fid))
    check(
        "invariant: no open question restates a rendered same-desk finding id",
        not restated,
        f"{restated[:4]} — a follow-up on a finding renders under it, not as a second unknown",
    )

    # --- prose vs coordinates vs the script
    prose_mismatch, phantom = [], []
    for f in flags:
        named = set(_SID.findall(_body(f)))
        stray = named - set(f.get("scene_ids") or [])
        if stray:
            prose_mismatch.append((f.get("flag_id"), sorted(stray)))
        if scene_meta:
            missing = named - set(scene_meta)
            if missing:
                phantom.append((f.get("flag_id"), sorted(missing)))
    check(
        "invariant: a finding's prose names no scene outside its coordinates",
        not prose_mismatch,
        f"prose-vs-coordinates: {prose_mismatch[:6]}",
    )
    check(
        "invariant: a finding's prose names no scene the script does not have",
        not phantom,
        f"phantom scenes: {phantom[:6]} — S049 in a 45-scene script (Reservoir Dogs case)",
    )

    # --- rating findings
    rating = [f for f in flags if str(f.get("category") or "").startswith("rating_")]
    stat_in_prose = [f["flag_id"] for f in rating if re.search(r"\d\s*%|\bn\s*=\s*\d", _body(f))]
    check(
        "invariant: rating findings carry no bare %/n= in prose (numbers live in citations)",
        not stat_in_prose,
        f"rating findings with a statistic loose in prose: {stat_in_prose[:6]}",
    )
    rule_shaped = []
    for f in rating:
        m = _NORMATIVE_RULE_RE.search(_body(f))
        if m:
            rule_shaped.append((f["flag_id"], m.group(0)[:40]))
    for n in r.get("adjudication_notes") or []:
        m = _NORMATIVE_RULE_RE.search(n)
        if m:
            rule_shaped.append(("adjudication", m.group(0)[:40]))
    check(
        "invariant: no rating finding asserts a normative CARA rule",
        not rule_shaped,
        f"rule-shaped rating claims: {rule_shaped[:4]}",
    )
    no_marginal = [f["flag_id"] for f in rating if not f.get("marginal")]
    _target = ((r.get("report") or {}).get("rating_prediction") or {}).get("target")
    _order = ["G", "PG", "PG-13", "R", "NC-17"]
    over_bound = []
    if _target in _order:
        for f in rating:
            dist = (f.get("marginal") or {}).get("distribution") or {}
            above = 0.0
            for rt, share in dist.items():
                try:
                    pct = float(str(share).rstrip("%"))
                except ValueError:
                    continue
                if rt in _order and _order.index(rt) > _order.index(_target):
                    above += pct / 100.0
            if dist and above < 0.5 and f.get("severity") in ("BLOCKER", "HIGH", "MEDIUM"):
                over_bound.append((f["flag_id"], round(above, 2)))
    contract_fires = [
        g for g in (r.get("guard_manifest") or []) if g.get("guard") == "contract_after_gates"
    ]
    check(
        "invariant: no assembled flag failed the contract after the gates (a code bug)",
        not contract_fires,
        f"contract_after_gates fired {len(contract_fires)}x: {contract_fires[:1]}",
    )
    check(
        "invariant: a rating finding at/under the target by its own marginal is never MEDIUM+",
        not over_bound,
        f"severity above the marginal's evidence: {over_bound[:3]}",
    )
    check(
        "invariant: every rendered rating finding carries its measured marginal",
        not no_marginal,
        f"rating findings without a structured marginal: {no_marginal[:4]}",
    )
    gate_fired = any(g.get("guard") == "marginal_hard_gate" for g in r.get("guard_manifest") or [])
    score = rep.get("greenlight_score")
    check(
        "invariant: a marginal-gate demotion that guts the ratings desk never scores",
        not (gate_fired and not rating and score is not None),
        f"gate left ZERO rating findings yet score={score}",
    )

    # --- the prediction panel
    pred = rep.get("rating_prediction") or {}
    beats = pred.get("beats_to_cut") or []
    rule_beats = [b[:60] for b in beats if _NORMATIVE_RULE_RE.search(b or "")]
    check(
        "invariant: no cut-list beat asserts a normative CARA rule",
        not rule_beats,
        f"rule-shaped beats: {rule_beats[:3]}",
    )
    predicted, target = pred.get("predicted"), pred.get("target")
    if pred and predicted in RATING_RANK and target in RATING_RANK:
        exceeds = RATING_RANK[predicted] > RATING_RANK[target]
        check(
            "invariant: cut list present iff the prediction exceeds the target",
            bool(beats) == exceeds,
            f"predicted {predicted} vs target {target}: {len(beats)} beats — a cut list "
            "'toward R' under a predicted R contradicts the panel; a missing one under a "
            "prediction above target leaves the producer without levers",
        )
    else:
        check(
            "invariant: cut list present iff the prediction exceeds the target",
            True,
            "no target on record — nothing to compare",
        )
    conf_set = pred.get("conformal_set") or []
    # batch 4: the set's inputs and the set itself must be coherent with the record
    from greenlight.tools.toolbelt import _boundary_data, _marginal_families

    _bd = _boundary_data()
    floor_missing = []
    for dsc in pred.get("descriptors") or []:
        m = _bd["marginals"].get(dsc)
        if not m:
            continue
        n = sum(m.values())
        rating, count = max(m.items(), key=lambda kv: kv[1])
        if n >= 50 and count / n >= 0.90 and conf_set and rating not in conf_set:
            floor_missing.append((dsc, rating))
    check(
        "invariant: a rating one descriptor carries at >=90% stays in the coverage set",
        not floor_missing,
        f"dominant descriptors excluded from the set: {floor_missing[:3]}",
    )
    _rej_rating = [
        f
        for f in (r.get("rejected_flags") or [])
        if str(f.get("category") or "").startswith("rating_")
    ]
    _kept_fams: set[str] = set()
    for f in flags:
        if str(f.get("category") or "").startswith("rating_"):
            _kept_fams.update(_marginal_families(str(f.get("category") or "")))
    _gone_fams: set[str] = set()
    for f in _rej_rating:
        _gone_fams.update(
            fam for fam in _marginal_families(str(f.get("category") or "")) if fam not in _kept_fams
        )
    stale_desc = [
        d
        for d in (pred.get("descriptors") or [])
        if any(d == g or d.endswith(" " + g) for g in _gone_fams)
    ]
    check(
        "invariant: the coverage set rests on no descriptor whose only finding was rejected",
        not stale_desc,
        f"descriptors from rejected-only families: {stale_desc[:3]}",
    )
    _count_re = re.compile(r"\b(\d{1,3})\s+scenes\b", re.IGNORECASE)
    over_count = [
        (
            f["flag_id"],
            max(int(x) for x in _count_re.findall(_body(f))),
            len(f.get("scene_ids") or []),
        )
        for f in flags
        if _count_re.findall(_body(f))
        and max(int(x) for x in _count_re.findall(_body(f))) > len(f.get("scene_ids") or [])
    ]
    check(
        "invariant: a finding's prose never counts more scenes than its coordinates show",
        not over_count,
        f"prose count > coordinates: {over_count[:3]}",
    )
    check(
        "invariant: a prediction outside its conformal set states a divergence reason",
        not pred or not conf_set or predicted in conf_set or bool(pred.get("divergence_reason")),
        f"predicted {predicted} not in {conf_set} with no divergence_reason",
    )
    comps = pred.get("comparables") or []
    if comps:
        recomputed = comps_weighted_majority(comps)
        check(
            "invariant: comps_majority equals the shared weighted vote over the comparables",
            pred.get("comps_majority") == recomputed,
            f"record says {pred.get('comps_majority')}, recompute says {recomputed}",
        )
        check(
            "every comparable excerpt is its own official rationale",
            all(
                re.match(
                    rf"^Rated\s+{re.escape(str(c.get('rating', '')))}\s+for\s+",
                    str(c.get("rationale", "")),
                    re.I,
                )
                for c in comps
            ),
            "rationale-space comparables (docs/plans/run17-rationale-space.md)",
        )
    descriptors = pred.get("descriptors") or []
    if descriptors and conf_set:
        try:
            reproduced = set(boundary_eval(list(descriptors)).get("prediction_set") or [])
            ok = reproduced == set(conf_set)
            detail = f"descriptors {descriptors} -> {sorted(reproduced)} vs record {conf_set}"
        except Exception as e:  # the asset is local; a failure here is a code bug
            ok, detail = False, f"boundary_eval failed: {type(e).__name__}"
        check("invariant: conformal set reproduces from the persisted descriptors", ok, detail)
    else:
        check(
            "invariant: conformal set reproduces from the persisted descriptors",
            True,
            "no descriptors on record (pre-B1 record) — not checkable",
        )

    # --- arithmetic reconciliation, derived not literal
    problems: list[str] = []
    counts = rep.get("counts") or {}
    for sev, n in counts.items():
        if n != sum(1 for f in flags if f.get("severity") == sev):
            problems.append(f"counts[{sev}]={n}")
    by_agent = rep.get("by_agent") or {}
    tally: dict[str, int] = {}
    for f in flags:
        tally[f.get("agent")] = tally.get(f.get("agent"), 0) + 1
    if {k: v for k, v in by_agent.items() if v} != tally:
        problems.append(f"by_agent {by_agent} vs {tally}")
    scored = [f for f in flags if not f.get("verification_unavailable")]
    lows = [
        f["remedy"]["est_cost_usd"][0]
        for f in scored
        if (f.get("remedy") or {}).get("est_cost_usd")
    ]
    highs = [
        f["remedy"]["est_cost_usd"][1]
        for f in scored
        if (f.get("remedy") or {}).get("est_cost_usd")
    ]
    cost = rep.get("est_clearance_cost_usd")
    if lows and (cost is None or abs(cost[0] - sum(lows)) > 0.5 or abs(cost[1] - sum(highs)) > 0.5):
        problems.append(f"cost {cost} vs [{sum(lows)}, {sum(highs)}]")
    days = [
        f["remedy"]["est_added_days"]
        for f in scored
        if (f.get("remedy") or {}).get("est_added_days") is not None
    ]
    if (max(days) if days else None) != rep.get("est_added_days"):
        problems.append(f"days {rep.get('est_added_days')} vs {max(days) if days else None}")
    paths = rep.get("est_cost_paths") or {}
    if paths and paths.get("as_written") and paths.get("target_rating"):
        ex = paths.get("excluded") or []
        ex_lo = sum((e.get("est_cost_usd") or [0, 0])[0] for e in ex)
        ex_hi = sum((e.get("est_cost_usd") or [0, 0])[1] for e in ex)
        if (
            abs(paths["as_written"][0] - paths["target_rating"][0] - ex_lo) > 0.5
            or abs(paths["as_written"][1] - paths["target_rating"][1] - ex_hi) > 0.5
        ):
            problems.append("est_cost_paths excluded != as_written - target")
    draft_pages = (r.get("draft") or {}).get("pages")
    if (
        draft_pages is not None
        and rep.get("page_count") is not None
        and draft_pages != rep.get("page_count")
    ):
        problems.append(f"pages draft={draft_pages} report={rep.get('page_count')}")
    check(
        "invariant: counts, by_agent, cost, days and pages reconcile with the flags",
        not problems,
        "; ".join(problems[:5]),
    )

    # --- the clearance log covers every scene, derived from the BUILT rows
    try:
        built = _binder.build(r)
        number_to_sid = {
            str(meta.get("number")): sid for sid, meta in scene_meta.items() if meta.get("number")
        }
        covered: set[str] = set()
        for row in built.get("rows") or []:
            covered |= expand_scene_label(str(row.get("Scene") or ""), number_to_sid)
        missing_rows = sorted(set(scene_meta) - covered)
        check(
            "invariant: clearance log covers every scene (a row per scene, derived from rows)",
            not scene_meta or not missing_rows,
            f"scenes no binder row accounts for: {missing_rows[:8]}",
        )
    except Exception as e:
        check(
            "invariant: clearance log covers every scene (a row per scene, derived from rows)",
            False,
            f"binder.build failed: {type(e).__name__}: {str(e)[:80]}",
        )

    # --- cleared-path honesty: no work-performed claim without a receipt
    work_claim = re.compile(
        r"negative check confirmed|confirmed no real[- ]world|search(?:es)? confirm(?:s|ed)? no",
        re.IGNORECASE,
    )
    research = r.get("research") or {}
    surf_by_id = {
        str(e.get("entity_id") or ""): str(e.get("surface") or "") for e in r.get("entities") or []
    }

    def _receipted(eid: str) -> bool:
        if eid and any(k.startswith(f"research:{eid}:") for k in research):
            return True
        low = surf_by_id.get(eid, "").lower()
        if len(low) < 4:
            return False
        return any(
            low in str(v.get("objective") or "").lower()
            or low in str(v.get("queries") or "").lower()
            for v in research.values()
            if isinstance(v, dict)
        )

    bad_claims = []
    for _desk, items in (r.get("cleared") or {}).items():
        for c in items or []:
            if not work_claim.search(str(c.get("reasoning") or "")):
                continue
            eid = str(c.get("entity_id") or "")
            if not _receipted(eid):
                bad_claims.append(eid or str(c.get("reasoning") or "")[:40])
    check(
        "invariant: no work-performed claim in cleared without a research receipt",
        not bad_claims,
        f"unreceipted claims survived assembly: {bad_claims[:4]}",
    )

    # --- uncited precision: statutes, years, rightsholders
    untraceable = []
    for f in flags:
        secs = _statute_sections(_body(f))
        if not secs:
            continue
        excerpts = " ".join(str(c.get("excerpt") or "") for c in f.get("citations") or [])
        missing = sorted(s for s in secs if s not in excerpts)
        if missing:
            untraceable.append((f["flag_id"], missing))
    check(
        "invariant: statute sections in findings trace to their own excerpts",
        not untraceable,
        f"typed-from-memory cites: {untraceable[:4]}",
    )
    arith = [(f["flag_id"], p) for f in flags for p in term_arithmetic_problems(_body(f))]
    check(
        "invariant: year + term arithmetic agrees with the stated expiry",
        not arith,
        f"{arith[:3]} — 1942 + 95 years is through 2037, not 2038",
    )
    names = [
        (f["flag_id"], untraceable_rightsholders(f))
        for f in flags
        if "license" in str(f.get("category") or "") and untraceable_rightsholders(f)
    ]
    check(
        "invariant: rightsholder names in license findings trace to their own excerpts",
        not names,
        f"{names[:4]} — an ownership claim naming a licensor no excerpt names is typed "
        "from memory (the statute-section rule, applied to names)",
    )

    # --- coverage: absence never renders as clean
    check(
        "invariant: no unexamined entities (every extracted item dispositioned)",
        not r.get("unexamined"),
        f"unexamined={[u.get('surface') for u in r.get('unexamined') or []][:8]}",
    )
    check(
        "invariant: no desk collapsed (worklist with zero dispositions)",
        not r.get("desks_incomplete"),
        f"desks_incomplete={r.get('desks_incomplete')}",
    )
    tc_cov = (r.get("desk_coverage") or {}).get("territory_censor") or {}
    check(
        "territory: all 12 axis sweeps dispositioned by work-item id",
        tc_cov.get("work_items_done", 0) >= 12,
        f"territory work_items_done={tc_cov.get('work_items_done')} "
        f"of {tc_cov.get('work_items_assigned')} assigned",
    )
    return checks

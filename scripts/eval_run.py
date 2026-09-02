#!/usr/bin/env python3
"""Score a run record against the seeded ground truth in fixtures/SEEDS.md.

Usage: python scripts/eval_run.py [runs/run_X.json]   (default: latest run)

This is the objective check for desk calibration: every seed the screenplay was
built around, expressed as an assertion over the run's kept flags. Not a unit test
— desks are non-deterministic — but every MISS here is a coverage failure to
explain before shipping a change to an instruction or the verifier.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys


def flags_matching(flags, *, category_any=None, scenes_any=None, desk=None, text_any=None):
    out = []
    for f in flags:
        if desk and f["agent"] != desk:
            continue
        if category_any and not any(c in f["category"] for c in category_any):
            continue
        if scenes_any and not set(f["scene_ids"]) & set(scenes_any):
            continue
        if text_any and not any(s in f["finding"].lower() for s in text_any):
            continue
        out.append(f)
    return out


def desk_addressed(record, desk, terms):
    """Did `desk` ADDRESS a topic — flag it, OR clear it with a reason that
    names it, OR note it as an open question?

    A desk that examines content and CLEARS it with a documented rationale has
    not missed it. The drug seed is the case: brief, non-graphic cannabis is a
    legitimate PG-13-boundary clearance, so a ratings desk that cleared it
    ("...establishing a PG-13 boundary") covered it exactly as well as one that
    filed a driver. Requiring a FLAG specifically failed a clean run on a
    defensible judgment call (2026-08-30 gate). This checks coverage — was the
    content examined — not which disposition the desk chose.
    """
    terms = [t.lower() for t in terms]
    for f in record.get("flags", []):
        if f.get("agent") != desk:
            continue
        blob = (f.get("category", "") + " " + f.get("finding", "")).lower()
        if any(t in blob for t in terms):
            return True
    for c in (record.get("cleared") or {}).get(desk, []):
        if any(t in str(c.get("reasoning", "")).lower() for t in terms):
            return True
    for q in (record.get("open_questions") or {}).get(desk, []):
        if any(t in str(q).lower() for t in terms):
            return True
    return False


def flags_about(flags, *, category_any=(), text_any=(), desk=None):
    """Category OR finding-text match — desks drift category slugs run to run."""
    # an empty filter must contribute NOTHING, not everything — a single-param
    # call once unioned in every flag and graded garbage (scale gate, 2026-08-26)
    by_cat = (
        flags_matching(flags, category_any=list(category_any), desk=desk) if category_any else []
    )
    by_text = flags_matching(flags, text_any=list(text_any), desk=desk) if text_any else []
    seen, out = set(), []
    for f in by_cat + by_text:
        if f["flag_id"] not in seen:
            seen.add(f["flag_id"])
            out.append(f)
    return out


def main() -> int:  # noqa: PLR0915, PLR0912 - a linear checklist, deliberately flat
    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else max(glob.glob("runs/run_*.json"), key=os.path.getmtime)
    )
    with open(path) as fh:
        r = json.load(fh)
    flags = r["flags"]
    rejected = r.get("rejected_flags", [])
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = ""):
        checks.append((name, ok, detail))

    # --- Clearance Counsel seeds
    sync = flags_matching(flags, category_any=["sync", "music"], desk="clearance_counsel")
    master = flags_matching(flags, category_any=["master"], desk="clearance_counsel")
    check("music: composition/sync flag", bool(sync), "the ownership chase, demo moment #2")
    check("music: separate master flag", bool(master), "sync and master must be two flags")
    check(
        "brand disparagement flagged",
        bool(flags_matching(flags, category_any=["disparagement"])),
        "Coors Light rant",
    )
    check(
        "tattoo flagged as visual artwork (Krane schooner)",
        bool(flags_about(flags, category_any=["artwork", "art_"], text_any=["tattoo", "krane"])),
        "depicted custom tattoo by a named artist — the Whitmill scenario",
    )
    check(
        "artwork flagged (Nighthawks)",
        bool(
            flags_about(flags, category_any=["artwork", "art_"], text_any=["nighthawks", "hopper"])
        ),
    )
    check(
        "likeness flagged (Springsteen photo)",
        bool(
            flags_about(
                flags,
                category_any=["publicity", "likeness", "personality"],
                text_any=["springsteen"],
            )
        ),
    )
    check(
        "film clip flagged (Jaws)",
        bool(flags_about(flags, category_any=["film_clip", "clip"], text_any=["jaws"])),
    )
    check(
        "no 'all clear' assertions filed as flags",
        not flags_matching(flags, category_any=["no_clearance", "no_action_required"]),
        "the report asserts risks, never certifies safety",
    )

    # --- Verifier traps: these must NOT survive as flags
    foster = flags_matching(flags, category_any=["sync", "music", "public_domain"])
    foster_bad = [
        f
        for f in foster
        if "hard times" in f["finding"].lower() or "foster" in f["finding"].lower()
    ]
    check(
        "trap: no license flag on the PD Stephen Foster hymn",
        not foster_bad,
        foster_bad[0]["flag_id"] if foster_bad else "",
    )
    thermos_bad = [
        f
        for f in flags_matching(flags, category_any=["trademark"])
        if "thermos" in f["finding"].lower()
    ]
    check("trap: no US trademark flag on 'Thermos'", not thermos_bad)

    # --- Ratings seeds
    lang = flags_matching(flags, category_any=["language"], desk="ratings_board")
    check("ratings: language flag exists", bool(lang))
    check(
        "ratings: language flag counts all 3 scenes",
        bool(flags_matching(lang, scenes_any=["S011"]))
        and bool(flags_matching(lang, scenes_any=["S003"])),
        "S003, S006, S011 — miscounting means find_in_script was skipped",
    )
    check(
        "ratings: drug use addressed (flagged or dispositioned)",
        desk_addressed(r, "ratings_board", ["drug", "cannabis", "marijuana", "joint", "smok"]),
        "the ratings desk must EXAMINE the drug content — a documented clearance "
        "at the PG-13 boundary counts; only silence is a miss",
    )

    # --- Safety seeds
    climax = flags_matching(flags, desk="safety_underwriter", scenes_any=["S009", "S010", "S011"])
    check(
        "safety: THE CLIMAX IS FLAGGED (S009-S011)",
        bool(climax),
        "burn+water+night+minor+animal — the worst scene cannot be the missed one",
    )
    check(
        "safety: firearms/salute flagged",
        bool(flags_matching(flags, desk="safety_underwriter", scenes_any=["S004", "S005"])),
    )

    # --- Territory seeds
    check(
        "territory: CN supernatural flag on the ghost scene",
        bool(
            flags_matching(
                flags, category_any=["supernatural", "superstition"], scenes_any=["S007"]
            )
        ),
    )
    check(
        "territory: CN or UAE drug flag",
        bool(
            flags_about(
                flags,
                category_any=["drug"],
                text_any=["marijuana", "joint", "drug"],
                desk="territory_censor",
            )
        ),
    )

    # --- Rating prediction (demo moment #3)
    pred = (r.get("report") or {}).get("rating_prediction")
    check(
        "rating prediction filed with comparables",
        bool(pred and len(pred.get("comparables", [])) >= 6),
        "query_precedent -> file_rating_prediction; needs the corpus loaded",
    )
    # Run 17: comparables come from cara_rationales — each row's excerpt is the
    # film's OFFICIAL rationale and must carry that row's own rating token
    # ("Rated R for ..." on an R row). A Wikipedia lead here means the corpus
    # regressed to plot-space; a token mismatch means corpus rows are mixed up.
    _comps = (pred or {}).get("comparables") or []
    check(
        "every comparable excerpt is its own official rationale",
        bool(_comps)
        and all(
            re.match(
                rf"^Rated\s+{re.escape(str(c.get('rating', '')))}\s+for\s+",
                str(c.get("rationale", "")),
                re.I,
            )
            for c in _comps
        ),
        "rationale-space comparables (docs/plans/run17-rationale-space.md)",
    )
    check(
        "cut list present when prediction exceeds target",
        bool(
            not pred
            or pred.get("predicted") in (pred.get("target"), None)
            or pred.get("beats_to_cut")
        ),
    )

    # --- Verification health
    verdicts = r.get("verdicts") or {}
    verdict_ids = {str(k).split(":")[0] for k in verdicts}
    kept_ids = {f.get("flag_id") for f in flags}
    check(
        "verification: ran on every kept flag, rejection rate <= 40%",
        bool(verdicts)
        and kept_ids <= verdict_ids
        and not any(f.get("verification_unavailable") for f in flags)
        and len(rejected) <= 0.4 * max(1, len(rejected) + len(flags)),
        f"{len(rejected)} rejected / {len(rejected) + len(flags)} filed; verdicts for "
        f"{len(verdict_ids)} flags — zero rejections is legitimate when the desks' filing "
        "gates already blocked the weak flags; a sleeping verifier shows as missing "
        "verdicts or fail-open markers, and those fail this check",
    )
    check(
        "invariant: every kept flag has a citation with an excerpt",
        all(f["citations"] and all(c["excerpt"].strip() for c in f["citations"]) for f in flags),
    )
    # run-8 assertions: the report may not reference a finding that doesn't
    # render, and a finding's prose may not name a scene outside its own
    # coordinates — both shipped visible self-contradictions this run.
    import re as _re

    rendered_ids = {f["flag_id"] for f in flags}
    dangling = [
        n
        for n in r.get("adjudication_notes", [])
        if not set(_re.findall(r"\bF\d{3,4}\b", n)) <= rendered_ids
    ]
    check(
        "invariant: no adjudication note references a non-rendered finding id",
        not dangling,
        f"dangling: {[n[:50] for n in dangling]}",
    )
    prose_mismatch = []
    for f in flags:
        body = f"{f.get('finding', '')} {(f.get('remedy') or {}).get('detail', '')}"
        stray = set(_re.findall(r"\bS\d{3}\b", body)) - set(f.get("scene_ids") or [])
        if stray:
            prose_mismatch.append((f["flag_id"], sorted(stray)))
    check(
        "invariant: a finding's prose names no scene outside its coordinates",
        not prose_mismatch,
        f"prose-vs-coordinates: {prose_mismatch[:6]}",
    )
    # A rating finding's marginal number must live in the citation the verifier can
    # trace to the corpus, never loose in the prose (where an untraceable "57% of 125"
    # was rejected as unsupported and read as fabrication). One place per percentage.
    stat_in_prose = []
    for f in flags:
        if not (f.get("category") or "").startswith("rating_"):
            continue
        body = f"{f.get('finding', '')} {(f.get('remedy') or {}).get('detail', '')}"
        if _re.search(r"\d\s*%|\bn\s*=\s*\d", body):
            stat_in_prose.append(f["flag_id"])
    check(
        "invariant: rating findings carry no bare %/n= in prose (numbers live in citations)",
        not stat_in_prose,
        f"rating findings with a statistic loose in prose: {stat_in_prose[:6]} — the marginal "
        "belongs in a rating_boundary citation, not the finding text",
    )
    # A rating finding may not assert a normative CARA rule ("directly commands an
    # R rating") — the corpus measures what CARA did, not what it requires, and a
    # rule-shaped claim is unverifiable by construction. The filing gate enforces
    # this; the assertion catches any path around it (adjudicator rewording, older
    # records).
    from greenlight.tools.toolbelt import _NORMATIVE_RULE_RE

    rule_shaped = []
    for f in flags:
        if not (f.get("category") or "").startswith("rating_"):
            continue
        body = f"{f.get('finding', '')} {(f.get('remedy') or {}).get('detail', '')}"
        m = _NORMATIVE_RULE_RE.search(body)
        if m:
            rule_shaped.append((f["flag_id"], m.group(0)[:40]))
    # text fields are fungible under a lexical gate: the Pro adjudicator writes
    # AFTER filing, so its notes are a surface the filing gate never sees
    for n in r.get("adjudication_notes", []):
        m = _NORMATIVE_RULE_RE.search(n)
        if m:
            rule_shaped.append(("adjudication", m.group(0)[:40]))
    check(
        "invariant: no rating finding asserts a normative CARA rule",
        not rule_shaped,
        f"rule-shaped rating claims: {rule_shaped[:4]} — state the descriptor-frequency "
        "observation, never what CARA 'requires'",
    )
    # run-13 item 3: the marginal must actually render — three runs of "the
    # plumbing works but nothing came out" is what a soft check buys.
    no_marginal = [
        f["flag_id"]
        for f in flags
        if (f.get("category") or "").startswith("rating_") and not f.get("marginal")
    ]
    check(
        "invariant: every rendered rating finding carries its measured marginal",
        not no_marginal,
        f"rating findings without a structured marginal: {no_marginal[:4]} — the hard "
        "gate should have demoted these",
    )
    # ...and the gate must never make the score BETTER: a demotion means the
    # ratings desk could not do its job, so the score is withheld.
    gate_fired = any(g.get("guard") == "marginal_hard_gate" for g in r.get("guard_manifest") or [])
    score = (r.get("report") or {}).get("greenlight_score")
    check(
        "invariant: a marginal-gate demotion that guts the ratings desk never scores",
        not (
            gate_fired
            and not any((f.get("category") or "").startswith("rating_") for f in flags)
            and score is not None
        ),
        f"gate left ZERO rating findings yet score={score} — a gutted desk must withhold; "
        "one demotion beside surviving marginals is an ordinary demotion and scores normally",
    )
    # the cut list is remedy surface too: no beat may assert a CARA rule
    beats = ((r.get("report") or {}).get("rating_prediction") or {}).get("beats_to_cut") or []
    rule_beats = [b[:60] for b in beats if _NORMATIVE_RULE_RE.search(b or "")]
    check(
        "invariant: no cut-list beat asserts a normative CARA rule",
        not rule_beats,
        f"rule-shaped beats: {rule_beats[:3]}",
    )
    # run-13 item 6d: the clearance log emits a row for EVERY scene — a log
    # that silently omits one contradicts its scene-by-scene premise. Derived
    # equality, never a literal count.
    from greenlight import binder as _binder

    cov = _binder.build(r).get("scene_coverage") or {}
    check(
        "invariant: clearance log covers every scene (rows == scenes)",
        cov.get("scenes") == cov.get("scenes_with_rows"),
        f"scenes={cov.get('scenes')} scenes_with_rows={cov.get('scenes_with_rows')}",
    )
    # run-13 item 1b: no cleared determination asserts completed research
    # without a receipt — the assembly rewrite should have fired.
    import re as _re2

    work_claim = _re2.compile(
        r"negative check confirmed|confirmed no real[- ]world|search(?:es)? confirm(?:s|ed)? no",
        _re2.IGNORECASE,
    )
    research = r.get("research") or {}
    surf_by_id = {
        str(e.get("entity_id") or ""): str(e.get("surface") or "") for e in r.get("entities") or []
    }

    def _receipted(eid: str) -> bool:
        # mirrors the assembly's two receipt arms: per-entity key OR a batch
        # sweep whose objective/query text names the surface — without the
        # second arm this check would false-fire on honest batch-swept claims
        if eid and any(k.startswith(f"research:{eid}:") for k in research):
            return True
        low = surf_by_id.get(eid, "").lower()
        min_surface = 4
        if len(low) < min_surface:
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
    # run-15 follow-up: uncited precision. A statute section a finding names must
    # appear in that finding's OWN citation excerpts — reader-traceable, not just
    # somewhere in the run's research (the filing gate covers that weaker bound).
    from greenlight.tools.toolbelt import _statute_sections

    untraceable = []
    for f in flags:
        body = f"{f.get('finding', '')} {(f.get('remedy') or {}).get('detail', '')}"
        secs = _statute_sections(body)
        if not secs:
            continue
        excerpts = " ".join(str(c.get("excerpt") or "") for c in f.get("citations") or [])
        missing = sorted(s for s in secs if s not in excerpts)
        if missing:
            untraceable.append((f["flag_id"], missing))
    check(
        "invariant: statute sections in findings trace to their own excerpts",
        not untraceable,
        f"typed-from-memory cites: {untraceable[:4]} — the reader must be able to "
        "verify a section number from the excerpt beside it",
    )
    check(
        "invariant: no unexamined entities (every extracted item dispositioned)",
        not r.get("unexamined"),
        f"unexamined={[u.get('surface') for u in r.get('unexamined') or []][:8]} — absence "
        "must never render as cleanliness",
    )
    tc_cov = (r.get("desk_coverage") or {}).get("territory_censor") or {}
    check(
        "territory: all 12 axis sweeps dispositioned by work-item id",
        tc_cov.get("work_items_done", 0) >= 12,
        f"territory work_items_done={tc_cov.get('work_items_done')} "
        f"of {tc_cov.get('work_items_assigned')} assigned — the 12 axis sweeps "
        "are now mechanical, not prompt folklore",
    )
    check(
        "invariant: no desk collapsed (worklist with zero dispositions)",
        not r.get("desks_incomplete"),
        f"desks_incomplete={r.get('desks_incomplete')} — the territory 5->0 failure class; "
        "silence must never grade as a clean bill",
    )

    print(f"\nEval of {path} — {len(flags)} kept, {len(rejected)} rejected\n")
    passed = 0
    for name, ok, detail in checks:
        mark = "\033[32mPASS\033[0m" if ok else "\033[31mMISS\033[0m"
        extra = f"  \033[2m{detail}\033[0m" if detail and not ok else ""
        print(f"  {mark}  {name}{extra}")
        passed += ok
    print(f"\n{passed}/{len(checks)}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

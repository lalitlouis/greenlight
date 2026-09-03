"""Review 2026-09-01 fix batch — toolbelt gates and rating tools (worker 2).

Every item here reproduced a defect first (docs/REVIEW-2026-09-01.md ids in the
test names); the assertions pin the deterministic behaviour that replaced it.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from test_toolbelt import CASSETTE, GOOD_CITATION, RESEARCH_EXCERPT, file_good_flag, make_ctx

from greenlight.tools import toolbelt

ASSET = json.loads(
    (Path(__file__).resolve().parents[1] / "src/greenlight/data/rating_boundary.json").read_text()
)
CORPUS_N = sum(ASSET["rating_totals"].values())


def _comp(rating, distance, title="X"):
    return {
        "title": title,
        "year": 2001,
        "rating": rating,
        "rationale": "r",
        "source_url": None,
        "distance": distance,
    }


# --- B3: the vote weight ------------------------------------------------------


def test_b3_exact_match_is_the_strongest_vote_not_the_weakest():
    comps = [_comp("PG-13", 0.0), _comp("R", 0.06), _comp("R", 0.07)]
    assert toolbelt.comps_weighted_majority(comps) == "PG-13"
    comps[0]["distance"] = 1e-5
    assert toolbelt.comps_weighted_majority(comps) == "PG-13"
    # a MISSING distance is still unknown (weighted as 1.0)
    assert toolbelt.comps_weighted_majority([{"rating": "PG"}, _comp("R", 0.06)]) == "R"


# --- B2: which marginal attaches ----------------------------------------------


def _file_rating(ctx, category, finding, cite):
    return toolbelt.file_flag(
        scene_ids=["S002"],
        severity="MEDIUM",
        category=category,
        finding=finding,
        citations=[{"excerpt": cite, "via": "local"}],
        remedy_action="REPLACE",
        remedy_detail="Trim at S002.",
        confidence=0.8,
        tool_context=ctx,
    )


def test_b2_marginal_named_in_the_finding_wins_over_unmodified():
    ctx = make_ctx(agent_name="ratings_board")
    r = toolbelt.rating_boundary(["brief drug use", "drugs"], ctx)
    cite = r["marginals"]["brief drugs"]["citation"]
    out = _file_rating(
        ctx,
        "rating_drug_use",
        "The joint in S003 matches the CARA descriptor 'brief drug use' in the corpus.",
        cite,
    )
    assert "Filed" in out, out
    m = toolbelt.desk_flags(ctx.state, "ratings_board")[-1]["marginal"]
    assert m["descriptor"] == "brief drugs"  # was 'unmodified drugs' (longest key)
    assert m["corpus_n"] == CORPUS_N and m["n"] == sum(ASSET["marginals"]["brief drugs"].values())


def test_b2_quoted_bare_descriptor_attaches_the_unmodified_marginal():
    ctx = make_ctx(agent_name="ratings_board")
    r = toolbelt.rating_boundary(["language", "strong language"], ctx)
    out = _file_rating(
        ctx,
        "rating_language",
        "Three uses match the CARA descriptor 'language', which patterns toward R.",
        r["marginals"]["language"]["citation"],
    )
    assert "Filed" in out, out
    assert toolbelt.desk_flags(ctx.state, "ratings_board")[-1]["marginal"]["descriptor"] == (
        "unmodified language"
    )


def test_b2_unnamed_prefers_qualified_over_unmodified_over_bare():
    ctx = make_ctx(agent_name="ratings_board")
    r = toolbelt.rating_boundary(["language", "strong language"], ctx)
    out = _file_rating(
        ctx,
        "rating_language",
        "The profanity profile sits at the PG-13/R boundary.",
        r["marginals"]["strong language"]["citation"],
    )
    assert "Filed" in out, out
    assert toolbelt.desk_flags(ctx.state, "ratings_board")[-1]["marginal"]["descriptor"] == (
        "strong language"
    )


def test_b2_marginal_last_merges_across_calls():
    ctx = make_ctx(agent_name="ratings_board")
    toolbelt.rating_boundary(["some violence"], ctx)
    r2 = toolbelt.rating_boundary(["pervasive language"], ctx)
    last = ctx.state["marginal_last:ratings_board"]
    assert "some violence" in last and "pervasive language" in last  # not overwritten
    out = _file_rating(
        ctx,
        "rating_violence",
        "The brawl matches 'some violence'.",
        r2["marginals"]["pervasive language"]["citation"],
    )
    assert "Filed" in out, out
    assert toolbelt.desk_flags(ctx.state, "ratings_board")[-1]["marginal"]["descriptor"] == (
        "some violence"
    )


def test_b2_every_vocabulary_family_can_carry_a_marginal():
    from greenlight.tools.toolbelt import _marginal_families

    assert _marginal_families("rating_nudity") == ["nudity"]
    assert "sexual_content" in _marginal_families("rating_sexuality")
    assert _marginal_families("rating_gore") == ["gore"]
    assert _marginal_families("rating_smoking") == ["smoking"]  # slug fallback
    assert "drugs" in _marginal_families("rating_drug_content")  # substring fallback
    ctx = make_ctx(agent_name="ratings_board")
    r = toolbelt.rating_boundary(["graphic nudity"], ctx)
    out = _file_rating(
        ctx,
        "rating_nudity",
        "The shower scene matches 'graphic nudity'.",
        r["marginals"]["graphic nudity"]["citation"],
    )
    assert "Filed" in out, out
    assert toolbelt.desk_flags(ctx.state, "ratings_board")[-1]["marginal"]["descriptor"] == (
        "graphic nudity"
    )


# --- B1: one descriptor per category ------------------------------------------


def test_b1_duplicates_of_one_category_collapse_to_the_most_specific():
    ctx = make_ctx(agent_name="ratings_board")
    stacked = toolbelt.rating_boundary(["language", "strong language", "brief drug use"], ctx)
    assert stacked["canonical_descriptors"] == ["strong language", "brief drugs"]
    clean = toolbelt.rating_boundary(
        ["strong language", "brief drug use"], make_ctx("ratings_board")
    )
    assert stacked["conformal_prediction_set"] == clean["conformal_prediction_set"]
    assert stacked["model_probabilities"] == clean["model_probabilities"]
    # the pure instrument agrees with the desk tool on identical input
    pure = toolbelt.boundary_eval(["language", "strong language", "brief drug use"])
    assert pure["canonical_descriptors"] == ["strong language", "brief drugs"]
    assert pure["prediction_set"] == stacked["conformal_prediction_set"]
    # every requested key still gets its marginal sentence (citations stay available)
    assert {"language", "unmodified language", "strong language", "brief drugs", "drugs"} <= set(
        stacked["marginals"]
    )


def test_b1_descriptors_persist_on_the_prediction():
    ctx = make_ctx("ratings_board", target_rating="PG-13")
    toolbelt.rating_boundary(["pervasive language", "some violence"], ctx)
    ctx.state["last_precedent:ratings_board"] = [_comp("R", 0.06)]
    msg = toolbelt.file_rating_prediction("R", "for pervasive language", ["Cut X at S002"], ctx)
    assert msg.startswith("Prediction filed"), msg
    pred = ctx.state["rating_prediction"]
    assert pred["descriptors"] == ["pervasive language", "some violence"]
    assert pred["conformal_set"] == ["R"]


# --- B5: one rounding, one derived corpus label --------------------------------


def test_b5_percentages_one_decimal_and_corpus_label_derived_from_the_asset():
    ctx = make_ctx(agent_name="ratings_board")
    r = toolbelt.rating_boundary(["pervasive language"], ctx)
    m = ctx.state["marginal_last:ratings_board"]["pervasive language"]
    assert all(v.endswith("%") and "." in v for v in m["distribution"].values())
    assert all(v.endswith("%") and "." in v for v in m["base_rate"].values())
    assert m["corpus_n"] == CORPUS_N
    assert f"{CORPUS_N:,}" in r["source"] and f"{CORPUS_N:,}" in m["source"]
    assert "4,544" not in toolbelt.__doc__ if toolbelt.__doc__ else True
    # R share of the parsed corpus, rounded like the comparables panel (one decimal)
    expected_r = f"{100 * ASSET['rating_totals']['R'] / CORPUS_N:.1f}%"
    assert m["base_rate"]["R"] == expected_r


# --- B10: rationale-space thresholds ------------------------------------------


def test_b10_near_conflict_only_for_an_identical_rationale_and_never_same_story():
    ctx = make_ctx("ratings_board", target_rating="PG-13")
    # 0.06 is an ordinary rationale-space neighbour: no near-identity leg
    ctx.state["last_precedent:ratings_board"] = [_comp("PG-13", 0.06), _comp("R", 0.07)]
    msg = toolbelt.file_rating_prediction("R", "for language", [], ctx, divergence_reason="x")
    assert (
        msg.startswith("Prediction filed")
        and ctx.state["rating_prediction"]["nearest_conflict"] is None
    )
    # an essentially identical rationale rated differently must be answered
    ctx.state["last_precedent:ratings_board"] = [_comp("PG-13", 0.004, "Twin"), _comp("R", 0.07)]
    msg = toolbelt.file_rating_prediction("R", "for language", [], ctx, divergence_reason="")
    assert msg.startswith("REJECTED") and "essentially identical" in msg
    assert "released form" not in msg and "same story" not in msg


def test_b10_spread_caution_only_when_the_neighbours_split(monkeypatch):
    monkeypatch.setenv("CLICKHOUSE_HOST", "h")
    monkeypatch.setenv("CLICKHOUSE_PASSWORD", "p")
    monkeypatch.setattr(toolbelt, "_embed", lambda text: [0.0])
    monkeypatch.setattr(toolbelt, "_corpus_base_rates", lambda: {"R": 56.2})
    rows_holder = {}

    class _Res:
        def __init__(self, rows):
            self.result_rows = rows

    class _Client:
        def query(self, *a, **kw):
            return _Res(rows_holder["rows"])

    monkeypatch.setattr(toolbelt, "_clickhouse_client", _Client)
    rows_holder["rows"] = [
        ("A", 2001, "R", "Rated R for language.", None, 0.05 + i / 1000) for i in range(8)
    ]
    out = asyncio.run(toolbelt.query_precedent("for language", 8, make_ctx("ratings_board")))
    assert "caution" not in out  # unanimous R at spread 0.007: the norm, not a warning
    rows_holder["rows"][0] = ("B", 2001, "PG-13", "Rated PG-13 for language.", None, 0.05)
    out = asyncio.run(toolbelt.query_precedent("for language", 8, make_ctx("ratings_board")))
    assert "caution" not in out  # 7 of 8 R is a clear plurality, not a split (batch 4)
    for k in range(4):
        rows_holder["rows"][k] = (
            "B",
            2001,
            "PG-13",
            "Rated PG-13 for language.",
            None,
            0.05 + k / 1000,
        )
    out = asyncio.run(toolbelt.query_precedent("for language", 8, make_ctx("ratings_board")))
    assert "plurality" in out["caution"] and "base rate" in out["caution"]


# --- B11: the normative-rule regex ----------------------------------------------


def test_b11_rating_token_is_a_word_and_count_rules_are_caught():
    from greenlight.tools.toolbelt import _NORMATIVE_RULE_RE as R

    for ok in (
        "stays within reasonable limits",
        "within Ratings Board guidelines",
        "within regulatory limits",
        "content of this kind typically draws an R in official rationales",
        "retain no more than 3 takes of the stunt",
    ):
        assert R.search(ok) is None, ok
    for rule in (
        "remains within PG-13 parameters",
        "requires an R rating",
        "more than one F-word triggers R",
        "two or more uses typically draw an R",
        "more than one use automatically triggers an R",
        "retaining no more than 1 isolated use to conform to PG-13 limits",
        "retain at most 1 F-word to stay PG-13",
        "retaining at most 1 non-sexual use",
    ):
        assert R.search(rule) is not None, rule


# --- A7: token-anchored figure traceability -------------------------------------


def test_a7_hour_caps_and_sections_need_the_token_not_a_substring():
    from greenlight.tools.toolbelt import _hour_present, _section_present

    assert not _hour_present("4", "revenue rose in 2024")
    assert _hour_present("4", "may work a maximum of 4 hours per day")
    assert _hour_present("4", "a 4-hour school day") and _hour_present("4.5", "4.5 hours")
    assert not _section_present("933", "a fee of $1,933 applies")
    assert _section_present("933", "14 U.S.C. § 933 provides") and _section_present(
        "1910", "29 CFR 1910.28"
    )
    ctx = make_ctx(agent_name="safety_underwriter", **{"research_budget:safety_underwriter": 3})
    toolbelt._register_provenance(ctx, ["Studio revenue rose in 2024 across the sector."])
    out = toolbelt.file_flag(
        scene_ids=["S002"],
        severity="MEDIUM",
        category="minor_safety",
        finding="A 10-year-old may work at most 4 hours on a school day.",
        citations=[
            {"excerpt": "Studio revenue rose in 2024 across the sector.", "url": "https://x.org/a"}
        ],
        remedy_action="ADD_SPECIALIST",
        remedy_detail="Studio teacher.",
        confidence=0.8,
        tool_context=ctx,
    )
    assert "REJECTED" in out and "4 hours" in out


# --- A10: citation quality -----------------------------------------------------


def test_a10_statute_attach_refuses_a_title_fragment_and_takes_a_provision():
    from greenlight.tools.toolbelt import _provision_span

    title = "14 USC 933 - Coast Guard ensigns and"
    assert _provision_span("933", [(title.lower(), title)]) is None
    prov = (
        "Under 14 U.S.C. § 933, the Coast Guard ensign and pennant may not be displayed "
        "by any vessel or person without authority; violations are punishable by fine."
    )
    span = _provision_span("933", [(title.lower(), title), (prov.lower(), prov)])
    assert span and "933" in span and len(span.split()) >= 8


def test_a10_registration_number_forms_are_caught():
    ctx = make_ctx()
    for text in (
        "U.S. Reg. No. 1234567",
        "Registration No. 2345678",
        "Registration Number 3456789",
    ):
        assert toolbelt._unverified_regs(ctx, f"The mark ({text}) is live.") is not None, text


def test_a10_word_overlap_hit_files_marked_repaired():
    ctx = make_ctx()
    toolbelt._register_provenance(ctx, [RESEARCH_EXCERPT])  # the registry, as a live run has
    scrambled = " ".join(reversed(RESEARCH_EXCERPT.split()))  # same tokens, wrong order
    out = file_good_flag(ctx, citations=[{**GOOD_CITATION, "excerpt": scrambled}])
    assert "Filed" in out, out
    cit = toolbelt.desk_flags(ctx.state, "clearance_counsel")[-1]["citations"][0]
    assert cit.get("repaired") is True


def test_a10_repair_repoints_the_url_to_the_source_of_the_excerpt():
    ctx = make_ctx()
    other = (
        "Trade libel occurs when a product or service is falsely accused of some bad "
        "attribute in a commercial publication or broadcast."
    )
    toolbelt._register_results(
        ctx, [{"url": "https://law.example.org/libel", "title": "t", "excerpts": [other]}]
    )
    near_miss = other.replace("falsely accused", "falsely accused on screen")
    out = file_good_flag(
        ctx, citations=[{"url": "https://www.copyright.gov/clearance", "excerpt": near_miss}]
    )
    assert "Filed" in out, out
    cit = toolbelt.desk_flags(ctx.state, "clearance_counsel")[-1]["citations"][0]
    assert cit["repaired"] is True and cit["url"] == "https://law.example.org/libel"


def test_a10_host_classifiers():
    from greenlight.tools.toolbelt import (
        _host_root,
        _is_authority_host,
        _is_background_host,
    )

    assert _is_background_host("https://Reddit.com/r/x")  # case
    assert _is_background_host("WWW.Fandom.com/wiki")  # scheme-less, still a host
    assert not _is_background_host("uspto.gov/trademarks")
    assert _is_authority_host("uspto.gov/trademarks")
    assert _is_authority_host("https://dir.ca.gov/dlse")  # state .gov
    assert not _is_authority_host("https://ca.gov.example.com/x")  # gov not the TLD
    assert not _is_authority_host("https://in.gov.br/x")
    assert not _is_authority_host("https://highpointnc.gov/x")
    assert _host_root("https://darkroom.bbfc.co.uk/x") == "bbfc.co.uk"
    assert _host_root("https://news.example.co.uk/x") == "example.co.uk"


def test_a10_local_tool_citations_are_never_background_and_carry_medium():
    from greenlight.tools.toolbelt import _background_only_problem, _is_local_tool_cite

    ctx = make_ctx(agent_name="safety_underwriter")
    out = toolbelt.csatf_bulletin("firearms", ctx)
    _num, title = next(iter(out["matches"].items()))
    local = {"via": "local", "excerpt": title, "source_type": "rules_table"}
    assert _is_local_tool_cite(local, ctx)
    assert _background_only_problem("MEDIUM", [local], ctx) is None
    # a web excerpt relabelled `local` borrows nothing
    faked = {"via": "local", "excerpt": RESEARCH_EXCERPT, "source_type": "rules_table"}
    assert not _is_local_tool_cite(faked, ctx)


# --- sync/master, cost span, cut list, prose scenes -----------------------------


def test_sync_finding_bundling_master_recording_license_rejected():
    ctx = make_ctx()
    out = file_good_flag(
        ctx,
        category="sync_license",
        finding="Sync license from the publisher; a master recording license is also needed.",
    )
    assert "REJECTED" in out and "master" in out.lower()


def test_cost_span_free_plus_paid_path_rejected_but_free_line_change_files():
    assert "REJECTED" in file_good_flag(make_ctx(), est_cost_usd_low=0, est_cost_usd_high=5000)
    assert "Filed" in file_good_flag(make_ctx(), est_cost_usd_low=0, est_cost_usd_high=0)
    assert "Filed" in file_good_flag(make_ctx(), est_cost_usd_low=0, est_cost_usd_high=500)


def test_b6_cut_list_dropped_when_prediction_is_at_or_below_target():
    assert (
        toolbelt.rating_rank("PG-13") < toolbelt.rating_rank("R")
        and toolbelt.rating_rank("x") == -1
    )
    ctx = make_ctx("ratings_board", target_rating="R")
    ctx.state["last_precedent:ratings_board"] = [_comp("R", 0.06)]
    msg = toolbelt.file_rating_prediction("R", "for language", ["Cut 'fucking' at S003"], ctx)
    assert msg.startswith("Prediction filed") and "Cut list dropped" in msg
    assert ctx.state["rating_prediction"]["beats_to_cut"] == []
    assert any(
        e.get("guard") == "cut_list_dropped_at_target"
        for e in ctx.state["guard_manifest:ratings_board"]
    )
    ctx2 = make_ctx("ratings_board", target_rating="PG-13")
    ctx2.state["last_precedent:ratings_board"] = [_comp("R", 0.06)]
    toolbelt.file_rating_prediction("R", "for language", ["Cut 'fucking' at S003"], ctx2)
    assert ctx2.state["rating_prediction"]["beats_to_cut"] == ["Cut 'fucking' at S003"]


def test_a6_prose_naming_a_nonexistent_scene_is_rejected():
    out = file_good_flag(make_ctx(), finding="In S099 the brand is disparaged on screen.")
    assert "REJECTED" in out and "S099" in out and "do not exist" in out


# --- B16: accounting -----------------------------------------------------------


def test_b16_desk_budget_left_adds_retry_allowance_to_the_base():
    state = {"research_budget:ratings_board": 5, "research_budget:ratings_board__retry": 12}
    assert toolbelt.desk_budget_left(state, "ratings_board") == 17  # was 12
    state = {
        "research_budget:clearance_counsel": 40,
        "research_budget:clearance_counsel__b1": 3,
        "research_budget:clearance_counsel__b2": 4,
        "research_budget:clearance_counsel__sweep": 12,
    }
    assert toolbelt.desk_budget_left(state, "clearance_counsel") == 19


def test_b16_deep_research_allowance_is_per_desk_family(monkeypatch):
    monkeypatch.setattr(toolbelt, "_durable_cache_load", lambda k: None)
    ctx = make_ctx(
        agent_name="clearance_counsel__b2",
        **{"deep_used:clearance_counsel__b1": 2, "research_budget:clearance_counsel__b2": 9},
    )
    out = asyncio.run(toolbelt.deep_research("who owns the master?", "E001", ctx))
    assert "allowance spent" in out["error"]


def test_b16_done_credits_open_questions_by_whole_word():
    ctx = make_ctx(
        agent_name="territory_censor",
        triage={
            "territory_censor": [{"entity_id": "E9", "surface": "Ford", "work_item_id": "TC-W001"}]
        },
        **{"research_budget:territory_censor": 10},
    )
    ctx.state["open_questions:territory_censor"] = ["We cannot afford to license this."]
    assert toolbelt.done("finished", ctx).startswith("NOT CLOSED")
    ctx.state["open_questions:territory_censor"] = ["Ford Mustang ownership unclear."]
    assert toolbelt.done("finished", ctx).startswith("Desk closed")


def test_b16_bare_string_queries_reach_the_live_search_as_a_list(monkeypatch):
    monkeypatch.setattr(toolbelt, "_durable_cache_load", lambda k: None)
    monkeypatch.setattr(toolbelt, "_durable_cache_store", lambda k, r: None)
    seen = {}

    def fake_search(objective, queries, session_id=None, country="", include_domains=None):
        seen["queries"] = queries
        return CASSETTE

    monkeypatch.setattr(toolbelt, "_live_search", fake_search)
    asyncio.run(toolbelt.research("q", "coors light disparagement", "E001", make_ctx()))
    assert seen["queries"] == ["coors light disparagement"]


def test_dominant_descriptor_floor_keeps_r_in_the_set():
    """Live Hangover report: 'pervasive language' (R in ~99% of 187 rationales)
    with two PG-13-shaped descriptors narrowed the set to {PG-13}. A rating one
    descriptor carries at >= 90% of >= 50 films cannot leave the set."""
    from greenlight.tools.toolbelt import boundary_eval

    ev = boundary_eval(
        ["pervasive language", "crude sexual content", "some violence", "thematic elements"]
    )
    assert "R" in ev["prediction_set"]
    assert any(f.startswith("pervasive language") for f in ev["set_floor"])
    soft = boundary_eval(["language", "brief drugs"])
    assert soft["set_floor"] == []  # 'language' alone is ~80% R — no floor


def test_recompute_boundary_after_rating_rejection():
    from greenlight.agents.verification import _recompute_boundary_after_drop

    pred = {
        "predicted": "R",
        "descriptors": ["pervasive language", "unmodified drugs"],
        "conformal_set": ["PG-13"],
    }
    dropped = [{"flag_id": "F2005", "category": "rating_drug_use"}]
    kept_no_drugs = [{"flag_id": "F2001", "category": "rating_language"}]
    new, note = _recompute_boundary_after_drop(pred, dropped, kept_no_drugs)
    assert note and note["dropped_descriptors"] == ["unmodified drugs"]
    assert new["descriptors"] == ["pervasive language"] and "R" in new["conformal_set"]
    assert new["reconciled_after_verification"] is True
    # a family another SURVIVING rating finding still carries stays
    kept_with_drugs = [*kept_no_drugs, {"flag_id": "F2009", "category": "rating_drug_use"}]
    same, none = _recompute_boundary_after_drop(pred, dropped, kept_with_drugs)
    assert none is None and same is pred


def test_scene_count_claim_must_match_coordinates():
    from greenlight.tools.toolbelt import _scene_count_problem

    ids = ["S007", "S008", "S012"]
    problem = _scene_count_problem("Mandalay Bay is the setting across 15 scenes.", "", ids)
    assert problem and "15 scenes" in problem and "3 scene id" in problem
    assert _scene_count_problem("Appears in 3 scenes (S007, S008, S012).", "", ids) is None
    assert _scene_count_problem("A recurring location across the script.", "", ids) is None


def test_rating_severity_bounded_by_marginal_mass_above_target():
    from types import SimpleNamespace

    from greenlight.tools.toolbelt import _bound_rating_severity

    ctx = SimpleNamespace(agent_name="ratings_board", state={"target_rating": "PG-13"})
    soft = {"descriptor": "unmodified thematic", "distribution": {"PG-13": "58.2%", "PG": "41.4%"}}
    flag = {"flag_id": "F2003", "severity": "MEDIUM"}
    _bound_rating_severity(ctx, flag, soft)
    assert flag["severity"] == "LOW" and flag["_severity_bounded"] is True
    hard = {"descriptor": "some violence", "distribution": {"R": "65.3%", "PG-13": "27.0%"}}
    flag2 = {"flag_id": "F2005", "severity": "MEDIUM"}
    _bound_rating_severity(ctx, flag2, hard)
    assert flag2["severity"] == "MEDIUM"
    ctx.state["target_rating"] = "R"
    flag3 = {"flag_id": "F2001", "severity": "HIGH"}
    _bound_rating_severity(
        ctx, flag3, {"descriptor": "pervasive language", "distribution": {"R": "99.5%"}}
    )
    assert flag3["severity"] == "LOW"  # R content against an R target is not a risk above target

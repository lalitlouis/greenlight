"""What-If simulator: the measured boundary is the primary instrument for a
post-cut profile.

The Swearnet-neighbors run (2026-09-01): cutting to one F-word produced the
revised rationale "for brief strong language" — a profile the corpus scores
PG-13 in 89% of 384 rationales — yet the kNN verdict stayed R, because a
five-word rationale embeds next to films rated R/NC-17 *solely* for language.
These tests pin the fix: descriptor parsing, the pure boundary evaluation, and
the basis rule that decides which instrument answers.
"""

from greenlight.tools.toolbelt import boundary_eval
from greenlight.whatif import _descriptor_phrases


def test_descriptor_phrases_bare_for():
    assert _descriptor_phrases("for brief strong language.") == ["brief strong language"]


def test_descriptor_phrases_rated_prefix_and_conjunctions():
    assert _descriptor_phrases(
        "Rated R for pervasive language, some violence and brief nudity."
    ) == ["pervasive language", "some violence", "brief nudity"]


def test_descriptor_phrases_curly_quoted():
    # The renderer quotes the revised profile; a pasted-back or quoted
    # rationale must still parse.
    assert _descriptor_phrases("“for some strong language.”") == ["some strong language"]


def test_boundary_eval_post_cut_language_profile_is_pg13():
    # Both revised profiles the simulator actually produced on the real run.
    for profile in ("brief strong language", "some strong language"):
        b = boundary_eval([profile])
        assert b["prediction_set"] == ["PG-13"], profile
        assert not b["unmatched"]
        # The specific marginal carries citable numbers.
        assert b["marginals"]["strong language"]["n"] >= 300


def test_boundary_eval_pervasive_profile_still_r():
    # Negative control: the boundary must NOT hand out PG-13 for uncut profiles.
    b = boundary_eval(["pervasive language", "some violence", "brief nudity"])
    assert b["prediction_set"] == ["R"]


def test_boundary_eval_unmatched_phrase_reported():
    b = boundary_eval(["brief strong language", "vibes of unease"])
    assert "vibes of unease" in b["unmatched"]
    assert b["matched"] == ["brief strong language"]


def test_basis_rule_matches_project_doctrine():
    # The inline rule in whatif.project(): boundary is the verdict ONLY when
    # every phrase matched and the conformal set is a single rating.
    def basis(b):
        s = b.get("prediction_set") or []
        return (
            "boundary"
            if s and len(s) == 1 and b.get("matched") and not b.get("unmatched")
            else "neighbors"
        )

    assert basis(boundary_eval(["brief strong language"])) == "boundary"
    # An unmatched phrase disqualifies the boundary — kNN answers.
    assert basis(boundary_eval(["brief strong language", "vibes of unease"])) == "neighbors"
    assert basis({}) == "neighbors"


# ---- 2026-09-01 review (B15): splitter re-binding, degraded payload, evidence ----


def test_descriptor_phrases_rebind_bare_intensity():
    # "strong, bloody violence" split as "strong" + "bloody violence" and the
    # boundary reported an unmatched "strong" — kNN answered instead, on
    # exactly the heavy-violence profiles. Mirror the harvest parser.
    assert _descriptor_phrases("Rated R for strong, bloody violence and language.") == [
        "strong bloody violence",
        "language",
    ]
    b = boundary_eval(_descriptor_phrases("for strong, bloody violence"))
    assert not b["unmatched"]


def test_project_degrades_when_neighbors_unavailable(monkeypatch):
    from greenlight import whatif

    record = {
        "script_title": "X",
        "report": {
            "rating_prediction": {
                "rationale": "for pervasive language, some violence and brief nudity",
                "beats_to_cut": ["Cut the F-words in S003"],
            }
        },
    }
    monkeypatch.setattr(whatif.storage, "load_research", lambda key: None)
    saved = {}

    def _save(key, val):
        saved[key] = val

    monkeypatch.setattr(whatif.storage, "save_research", _save)
    monkeypatch.setattr(whatif, "_revise_rationale", lambda r, cuts: "for brief strong language")

    def boom(*a, **k):
        raise RuntimeError("clickhouse down")

    monkeypatch.setattr(whatif, "_embed_cached", boom)
    out = whatif.project(record, "run1", [0])
    # the boundary narrows the revised profile to one rating, so it answers alone
    assert out["projected"] == "PG-13" and out["basis"] == "boundary"
    assert out["comparables"] == [] and out["neighbors_unavailable"] is True
    assert out["boundary"]["driver"]["descriptor"] in (
        "strong language",
        "brief language",
        "language",
    )
    assert not saved, "a degraded answer must never be cached"

    # when the boundary cannot narrow either, the payload is an honest error, not a 500
    monkeypatch.setattr(whatif, "_revise_rationale", lambda r, cuts: "for vibes of unease")
    out2 = whatif.project(record, "run1", [0])
    assert out2.get("unavailable") is True and "error" in out2


def test_project_rewrite_failure_is_an_honest_payload(monkeypatch):
    from greenlight import whatif

    record = {"report": {"rating_prediction": {"rationale": "for language", "beats_to_cut": ["x"]}}}
    monkeypatch.setattr(whatif.storage, "load_research", lambda key: None)

    def boom(*a, **k):
        raise RuntimeError("model down")

    monkeypatch.setattr(whatif, "_revise_rationale", boom)
    out = whatif.project(record, "run1", [0])
    assert out.get("unavailable") is True and "error" in out


def test_suggest_evidence_never_cites_neighbours_on_boundary_basis():
    from greenlight.whatif import suggest_evidence

    base = {
        "projected": "R",
        "basis": "boundary",
        "tally": {"R": 8},
        "boundary": {
            "driver": {"descriptor": "pervasive language", "n": 187, "distribution": {"R": "99%"}}
        },
    }
    line = suggest_evidence(base)
    assert "comparables" not in line and "pervasive language" in line and "99%" in line
    knn = suggest_evidence({"projected": "R", "basis": "neighbors", "tally": {"R": 6}})
    assert "6 still rate R" in knn


def test_driver_marginal_prefers_the_descriptor_that_draws_the_projection():
    from greenlight.whatif import _driver_marginal

    margs = [
        {"descriptor": "some violence", "n": 381, "distribution": {"R": "65%", "PG-13": "27%"}},
        {"descriptor": "pervasive language", "n": 187, "distribution": {"R": "99%"}},
        {"descriptor": "brief nudity", "n": 40, "distribution": {"R": "70%"}},
    ]
    assert _driver_marginal(margs, "R")["descriptor"] == "pervasive language"
    assert _driver_marginal(margs, "PG-13")["descriptor"] == "some violence"

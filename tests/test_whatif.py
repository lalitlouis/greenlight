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

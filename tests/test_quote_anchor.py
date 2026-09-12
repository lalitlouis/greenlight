"""Receipt provenance only; these checks never establish legal entailment."""

import json
from pathlib import Path

import pytest

from greenlight.agents.quote_anchor import anchor_quote


@pytest.mark.parametrize(
    ("source", "quote", "expected"),
    [
        ("must\n\t retain  permits.", "must retain permits.", "must\n\t retain  permits."),
        (
            "a **qualified specialist** is required",
            "a qualified specialist is required",
            "a **qualified specialist** is required",
        ),
        (
            '_**Case**_ , a [Court](https://example.org/court "Court") decision.',
            "Case , a Court decision.",
            'Case**_ , a [Court](https://example.org/court "Court") decision.',
        ),
        (
            "shall end no ### later than 10pm",
            "shall end no later than 10pm",
            "shall end no ### later than 10pm",
        ),
        ("Original exact text", "Original exact text", "Original exact text"),
    ],
)
def test_display_quote_maps_to_raw_substring(source, quote, expected):
    assert anchor_quote(quote, source) == expected
    assert expected in source


@pytest.mark.parametrize(
    ("source", "quote"),
    [
        ("must **not** employ minors", "must employ minors"),
        ("under **16** years", "under 18 years"),
        ("may **use** a specialist", "must use a specialist"),
        ("maintain **licenses**", "maintain firearms"),
        ("**must** apply if filming in California", "must apply in California"),
        ("keep **A** then B", "keep B then A"),
        ("keep **A**, B", "keep A B"),
        ("**Do not** proceed", "do not proceed"),
        ("**Rule** one. _Rule_ one.", "Rule one."),  # ambiguous display occurrence
        ("**Rule** #12 applies", "Rule 12 applies"),
        ("file_name **required**", "filename required"),
        ("use * quantity **required**", "use quantity required"),
        ("**The** [First", "The First"),  # truncated link is not repaired
        ("**The** ~~old rule~~", "The old rule"),  # strikeout is substantive
        ("**The** ![diagram](https://example.org/image)", "The diagram"),
        ("**The** [[nested]](https://example.org/page)", "The nested"),
        ("A **permit** is required", "mit is required"),
        ("Anything", " \n "),
    ],
)
def test_no_fuzzy_semantic_or_ambiguous_repair(source, quote):
    assert anchor_quote(quote, source) is None


@pytest.mark.parametrize(("fid", "expected_match"), [("F3006", True), ("F1008", False)])
def test_saved_formatting_failures(fid, expected_match):
    path = Path(__file__).resolve().parents[1] / "runs/run_20260911_015915.json"
    record = json.loads(path.read_text())
    flag = next(f for f in record["rejected_flags"] if f["flag_id"] == fid)
    after = record["verdicts"][fid]["evidence_review"]["after"]
    failed = next(c for c in after["claim_checks"] if c["status"] == "UNKNOWN")
    receipt = failed["support_spans"][0]
    source = flag["citations"][receipt["citation_number"] - 1]["excerpt"]
    result = anchor_quote(receipt["quote"], source)
    assert (result is not None) == expected_match
    if result is not None:
        assert result in source and "no ### later" in result


def test_saved_jury_instruction_spacing_returns_the_unmodified_source_receipt():
    path = Path(__file__).resolve().parents[1] / "runs/run_20260912_040149.json"
    record = json.loads(path.read_text())
    flag = next(f for f in record["rejected_flags"] if f["flag_id"] == "F1007")
    failed = next(
        c
        for c in record["verdicts"]["F1007"]["evidence_review"]["after"]["claim_checks"]
        if c["status"] == "UNKNOWN"
    )
    receipt = failed["support_spans"][1]
    raw = flag["citations"][receipt["citation_number"] - 1]["excerpt"]
    result = anchor_quote(receipt["quote"], raw)
    assert result in raw and "ornecessarilyunderstoodtohave" in result
    assert result != receipt["quote"]
    assert "".join(result.split()) == "".join(receipt["quote"].split())


@pytest.mark.parametrize(
    ("source", "quote"),
    [
        ("Therapist", "The rapist"),  # short word segmentation is ambiguous
        ("A permitisrequired for all work.", "A permit is permitted for all work."),
        ("A permitisnotrequired for all work.", "A permit is required for all work."),
        ("A permitisrequired for all work.", "A permit is required for some work."),
        ("A permitisrequired for all work.", "A permit is required for all works."),
        ("Apermitisrequired for all work.", "permit is required for all work."),
        (
            "A permitisrequired for all work. A permitisrequired for all work.",
            "A permit is required for all work.",
        ),
    ],
)
def test_spacing_repair_cannot_change_characters_conditions_or_choose_an_ambiguous_match(
    source, quote
):
    assert anchor_quote(quote, source) is None


def test_spacing_repair_does_not_pass_the_requested_word_segmentation_to_the_reviewer():
    source = "The therapist provides a service."
    assert anchor_quote("The the rapist provides a service.", source) == source

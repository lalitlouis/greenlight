"""Rule text cannot outrun the exact retrieved source snapshot that enabled it."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from greenlight.agents.source_rules import SourceBoundRepair, available_rules, bound_correction

ROOT = Path(__file__).resolve().parents[1]


def saved_fire_flag():
    return json.loads((ROOT / "fixtures/cassettes/fresh_safety_20260911.json").read_text())[
        "flags"
    ][0]


def firearm_flag():
    record = json.loads((ROOT / "runs/run_20260912_003816.json").read_text())
    return next(f for f in record["rejected_flags"] if f["flag_id"] == "F3003")


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("change", ["excerpt", "url", "via", "missing"])
def test_firearm_card_requires_both_unchanged_live_source_receipts(index, change):
    flag = firearm_flag()
    assert len(available_rules(flag)) == 1
    if change == "missing":
        flag["citations"].pop(index)
    else:
        flag["citations"][index][change] = {
            "excerpt": "Changed context or rule.",
            "url": "https://example.invalid",
            "via": "local",
        }[change]
    assert not available_rules(flag)


def test_firearm_card_preserves_complete_meeting_sentence_and_does_not_finish_roster():
    flag = firearm_flag()
    rules = available_rules(flag)
    proposal = SourceBoundRepair(
        finding="Rifle volleys are depicted; the actual production method is unconfirmed.",
        rule_ids=[rules[0]["rule_id"]],
        severity="HIGH",
    )
    patch, selected = bound_correction(proposal, rules)
    assert patch["remedy_action"] == "REPLACE"
    assert patch["remedy_detail"] == selected[0]["remedy_detail"]
    assert "all involved personnel" in patch["remedy_detail"]
    assert "before any firearm is used" in patch["remedy_detail"]
    assert "without on-set firing" in patch["remedy_detail"]
    assert "Property Master" not in patch["remedy_detail"]
    assert "designated production" not in patch["remedy_detail"]
    for order in (
        rules + available_rules(saved_fire_flag()),
        available_rules(saved_fire_flag()) + rules,
    ):
        mixed = SourceBoundRepair(
            finding=proposal.finding, rule_ids=[r["rule_id"] for r in order], severity="HIGH"
        )
        assert bound_correction(mixed, order)[0]["remedy_action"] == "ADD_SPECIALIST"


def test_retrieved_receipts_use_the_same_rule_on_the_re_source_path():
    flag = saved_fire_flag()
    before = available_rules(flag)
    for citation in flag["citations"]:
        citation["via"] = "parallel_search_resource"
    assert available_rules(flag) == before


@pytest.mark.parametrize("change", ["url", "excerpt", "via", "desk", "missing"])
def test_changed_or_missing_source_cannot_activate_a_known_rule(change):
    flag = saved_fire_flag()
    rules = available_rules(flag)
    assert len(rules) == 2
    original = deepcopy(flag)
    if change == "desk":
        flag["agent"] = "clearance_counsel"
    elif change == "missing":
        flag["citations"] = []
    else:
        for citation in flag["citations"]:
            citation[change] = {
                "url": "https://example.invalid",
                "excerpt": "Different rule.",
                "via": "local",
            }[change]
    assert available_rules(flag) == []
    assert all(
        rule["source_quote"] == original["citations"][rule["citation_number"] - 1]["excerpt"]
        for rule in rules
    )


def test_bound_remedy_uses_only_selected_rule_text_in_stable_order():
    flag = saved_fire_flag()
    original = deepcopy(flag)
    rules = available_rules(flag)
    proposal = SourceBoundRepair(
        finding="Depicted fire and night-water hazards.",
        rule_ids=[r["rule_id"] for r in reversed(rules)],
        severity="HIGH",
    )
    correction, selected = bound_correction(proposal, rules)
    assert flag == original
    assert selected == rules
    assert correction["remedy_detail"] == " ".join(r["remedy_detail"] for r in rules)
    assert correction["remedy_action"] == "ADD_SPECIALIST"
    assert "as applicable" in correction["remedy_detail"]
    assert "open flame" not in correction["remedy_detail"]
    assert "Marine Coordinator" not in correction["remedy_detail"]
    assert "lifeguard" not in correction["remedy_detail"]


@pytest.mark.parametrize("bad_id", ["invented", "repeated"])
def test_model_cannot_invent_or_repeat_rule_cards(bad_id):
    rules = available_rules(saved_fire_flag())
    first = rules[0]["rule_id"]
    proposal = SourceBoundRepair(
        finding="Fire hazard.",
        rule_ids=[first, "invented" if bad_id == "invented" else first],
        severity="HIGH",
    )
    with pytest.raises(ValueError):
        bound_correction(proposal, rules)


def test_water_only_selection_remains_a_specific_input_question_without_inventing_a_hire():
    rules = available_rules(saved_fire_flag())
    proposal = SourceBoundRepair(
        finding="Night-water exposure.", rule_ids=[rules[1]["rule_id"]], severity="HIGH"
    )
    correction, selected = bound_correction(proposal, rules)
    assert len(selected) == 1
    assert correction["remedy_action"] == "NO_ACTION"
    assert correction["remedy_detail"].startswith("Confirm whether cast or crew will work in water")
    assert "Pyrotechnic" not in correction["remedy_detail"]


def test_reviewed_context_variant_preserves_necessity_and_never_accepts_arbitrary_context():
    flag = json.loads(
        (ROOT / "fixtures/cassettes/prequalification_fresh_safety_20_20260911.json").read_text()
    )["flags"][0]
    rules = available_rules(flag)
    assert [r["rule_id"] for r in rules] == [
        "csatf16_pyrotechnics_licenses_2018",
        "csatf17_water_devices_accounting",
    ]
    assert rules[0]["matched_source_sha256"] in rules[0]["additional_reviewed_source_sha256"]
    proposal = SourceBoundRepair(
        finding="Fire and night-water hazards if staged practically.",
        rule_ids=[r["rule_id"] for r in rules],
        severity="HIGH",
    )
    correction, _ = bound_correction(proposal, rules)
    assert "as applicable" in correction["remedy_detail"]
    assert "If personnel will enter the water, determine whether" in correction["remedy_detail"]
    assert "for example" in correction["remedy_detail"]
    for citation in flag["citations"]:
        citation["excerpt"] += " These provisions apply only in a different situation."
    assert not available_rules(flag)  # matching a familiar sentence is not enough

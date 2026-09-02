"""CSATF bulletin numbers named in a finding must be carried by the flag's own
citations — the statute/licensor rule applied to bulletins (gate roll 2, 2026-09-01)."""

from __future__ import annotations

from types import SimpleNamespace

from greenlight.tools.toolbelt import (
    _bulletin_numbers,
    _is_local_tool_cite,
    _register_tool_output,
    _uncited_bulletin_problem,
)

_SEQ = iter(range(1, 10_000))


def _ctx():
    return SimpleNamespace(
        agent_name="safety_underwriter",
        state={},
        actions=SimpleNamespace(escalate=False),
        invocation_id=f"test-bulletin-{next(_SEQ)}",
    )


def test_bulletin_numbers_parse_singles_and_lists():
    assert _bulletin_numbers("Under CSATF Safety Bulletin #16 and 33 CFR Part 100") == {"16"}
    assert _bulletin_numbers("per Safety Bulletins #4 and #17 (Water Hazards)") == {"4", "17"}
    assert _bulletin_numbers("Bulletin 1 governs blanks") == {"1"}
    assert _bulletin_numbers("no bulletin named") == set()


def test_unretrieved_bulletin_rejects_with_add_not_replace_wording():
    cits = [
        {
            "url": "https://www.law.cornell.edu/cfr/text/33/100.501",
            "excerpt": "Captain of the Port Representative means a commissioned officer.",
        }
    ]
    problem = _uncited_bulletin_problem(_ctx(), "Under CSATF Safety Bulletin #16 ...", "", cits)
    assert problem and "16" in problem
    assert "KEEP every citation" in problem and "ADD" in problem
    assert len(cits) == 1  # nothing attached — the desk never verified the number


def test_csatf_url_or_excerpt_carries_the_number():
    ctx = _ctx()
    by_url = [
        {
            "url": "https://www.csatf.org/wp-content/uploads/2018/05/16PYROTECHNIC.pdf",
            "excerpt": "x",
        }
    ]
    assert _uncited_bulletin_problem(ctx, "Bulletin #16 applies.", "", by_url) is None
    by_slug = [{"url": "https://www.csatf.org/04_safety_bltn_stunts/", "excerpt": "x"}]
    assert _uncited_bulletin_problem(ctx, "Bulletins #4 and #17", "", by_slug) is not None
    by_slug.append(
        {"url": "https://example.org/x", "excerpt": "See Safety Bulletin #17, Water Hazards."}
    )
    assert _uncited_bulletin_problem(ctx, "Bulletins #4 and #17", "", by_slug) is None


def test_verified_number_auto_attaches_index_line_as_local_cite():
    ctx = _ctx()
    _register_tool_output(
        ctx,
        {"matches": {"16": "Recommended Guidelines For Safety With Pyrotechnic Special Effects"}},
    )
    cits = [
        {
            "url": "https://www.csatf.org/wp-content/uploads/2018/05/19FLAMES.pdf",
            "excerpt": "open flame",
        }
    ]
    assert _uncited_bulletin_problem(ctx, "Under Bulletin #16 and #19.", "", cits) is None
    attached = cits[-1]
    assert attached["via"] == "local" and attached["repaired"] is True
    assert "Pyrotechnic" in attached["excerpt"]
    assert _is_local_tool_cite(attached, ctx)


def test_unknown_bulletin_number_is_named_as_from_memory():
    problem = _uncited_bulletin_problem(_ctx(), "CSATF Bulletin #77 requires it.", "", [])
    assert problem and "do not exist in the official index" in problem

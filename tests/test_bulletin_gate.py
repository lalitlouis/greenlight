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
    # a third-party page that merely MENTIONS the number does not verify it
    by_slug.append(
        {"url": "https://example.org/x", "excerpt": "See Safety Bulletin #17, Water Hazards."}
    )
    assert _uncited_bulletin_problem(ctx, "Bulletins #4 and #17", "", by_slug) is not None
    by_slug.append({"url": "https://www.csatf.org/17_safety_bltn_water_hazards/", "excerpt": "x"})
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


def _flag_with(cits):
    import json
    from pathlib import Path

    r = json.loads(Path("runs/run_20260901_223815.json").read_text())
    flag = dict(r["flags"][0])
    flag["citations"] = cits
    flag.pop("marginal", None)
    return flag


def test_every_auto_attached_citation_validates_against_the_flag_schema():
    """Roll 3 died at build_report on an attached `source_type` outside the enum.
    Every auto-attach path must produce a citation the frozen schema accepts."""
    from greenlight.contracts import validate
    from greenlight.tools.toolbelt import (
        _register_provenance,
        _uncited_licensor_problem,
        _uncited_statute_problem,
    )

    ctx = _ctx()
    # bulletin index line
    _register_tool_output(
        ctx,
        {"matches": {"16": "Recommended Guidelines For Safety With Pyrotechnic Special Effects"}},
    )
    cits = [
        {
            "source_type": "web",
            "url": "https://www.csatf.org/wp-content/uploads/2018/05/19FLAMES.pdf",
            "excerpt": "open flame rules",
        }
    ]
    assert _uncited_bulletin_problem(ctx, "Under Bulletin #16.", "", cits) is None
    validate("flag", _flag_with(cits))
    # statute provision span
    prov = (
        "Under 14 U.S.C. § 933, the Coast Guard ensign and pennant may not be displayed "
        "by any vessel or person without authority; violations are punishable by fine."
    )
    _register_provenance(ctx, [prov], url="https://www.law.cornell.edu/uscode/text/14/933")
    cits2 = [
        {
            "source_type": "web",
            "url": "https://www.uscg.mil/x",
            "excerpt": "The emblem is protected.",
        }
    ]
    assert (
        _uncited_statute_problem(
            ctx, "government_insignia", "Under 14 U.S.C. § 933 the emblem is restricted.", "", cits2
        )
        is None
    )
    validate("flag", _flag_with(cits2))
    # licensor naming line
    _register_provenance(
        ctx,
        ["Hallelujah by Leonard Cohen. Copyright Sony Music Publishing (US) LLC, worldwide."],
        url="https://rep.example/h",
    )
    cits3 = [
        {
            "source_type": "web",
            "url": "https://easysong.example/x",
            "excerpt": "Composed by Leonard Cohen",
        }
    ]
    assert (
        _uncited_licensor_problem(
            ctx, "sync_license", "Controlled by Sony Music Publishing.", "", cits3
        )
        is None
    )
    validate("flag", _flag_with(cits3))


def test_attach_citation_refuses_a_malformed_shape_without_raising():
    from greenlight.tools.toolbelt import _attach_citation

    ctx = _ctx()
    cits = []
    ok = _attach_citation(ctx, cits, {"source_type": "safety_bulletin", "excerpt": "x"}, guard="t")
    assert ok is False and cits == []
    assert any(
        g.get("refused") == "citation shape"
        for g in ctx.state.get("guard_manifest:safety_underwriter", []) or _manifest_entries(ctx)
    )


def _manifest_entries(ctx):
    out = []
    for k, v in ctx.state.items():
        if str(k).startswith("guard_manifest") and isinstance(v, list):
            out.extend(v)
    return out

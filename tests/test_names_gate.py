"""Licensor-name traceability: one extractor (greenlight.names) shared by the
filing gate and both eval gates, plus the entity-identity guard on merges."""

from __future__ import annotations

from greenlight.names import rightsholder_names, untraceable_rightsholders


def test_case_citation_is_not_a_rightsholder():
    body = (
        "Exposure under Ringgold v. Black Entertainment Television; "
        "licensed by Artists Rights Society."
    )
    assert "Black Entertainment" not in " ".join(rightsholder_names(body))
    assert rightsholder_names(body) == ["Artists Rights Society"]


def test_slash_names_trace_through_tokens():
    body = "100% controlled by Sony Music Publishing (formerly Sony/ATV Music Publishing)."
    assert untraceable_rightsholders(body, "Copyright Sony/ATV Music Publishing") == []
    missing = untraceable_rightsholders(body, "Composed by Leonard Cohen")
    assert missing == ["Sony Music Publishing", "Sony/ATV Music Publishing"]


_SEQ = iter(range(1, 10_000))


def _ctx():
    from types import SimpleNamespace

    return SimpleNamespace(
        agent_name="clearance_counsel",
        state={},
        actions=SimpleNamespace(escalate=False),
        invocation_id=f"test-names-{next(_SEQ)}",  # isolate the process-local registries
    )


def test_licensor_gate_rejects_unretrieved_and_attaches_retrieved():
    from greenlight.tools.toolbelt import _register_provenance, _uncited_licensor_problem

    ctx = _ctx()
    finding = "The composition is 100% controlled by Sony Music Publishing for the Cohen estate."
    cits = [{"excerpt": "Composed by Leonard Cohen", "url": "https://easysong.example/x"}]
    problem = _uncited_licensor_problem(ctx, "sync_license", finding, "", cits)
    assert problem and "Sony Music Publishing" in problem and len(cits) == 1
    # the desk retrieved the repertory line but excerpted the wrong sentence:
    # auto-attach, never a refile
    _register_provenance(
        ctx,
        [
            "Hallelujah by Leonard Cohen. Copyright Sony Music Publishing (US) LLC, "
            "administered worldwide; contact the licensing department for sync quotes."
        ],
        url="https://repertory.example/hallelujah",
    )
    assert _uncited_licensor_problem(ctx, "sync_license", finding, "", cits) is None
    assert cits[-1]["repaired"] is True and "Sony Music Publishing" in cits[-1]["excerpt"]
    assert cits[-1]["url"] == "https://repertory.example/hallelujah"


def test_licensor_gate_ignores_non_licence_categories_and_case_cites():
    from greenlight.tools.toolbelt import _uncited_licensor_problem

    ctx = _ctx()
    assert (
        _uncited_licensor_problem(ctx, "stunt_pyro", "Warner Bros. Pictures owns it.", "", [])
        is None
    )
    body = "Exposure under Ringgold v. Black Entertainment Television."
    assert _uncited_licensor_problem(ctx, "artwork_license", body, "", []) is None


def test_dedupe_never_merges_two_entities():
    from greenlight.agents.adjudicator import merge_exact_duplicates

    def flag(fid, eid, scenes):
        return {
            "flag_id": fid,
            "agent": "clearance_counsel",
            "category": "artwork_license",
            "severity": "MEDIUM",
            "entity_id": eid,
            "scene_ids": scenes,
            "citations": [{"excerpt": fid}],
            "remedy": {"action": "OBTAIN_LICENSE"},
            "finding": fid,
        }

    kept = merge_exact_duplicates(
        [flag("F1", "E001", ["S002", "S007"]), flag("F2", "E009", ["S002"])]
    )
    assert [f["flag_id"] for f in kept] == ["F1", "F2"]
    same = merge_exact_duplicates([flag("F1", "E001", ["S002"]), flag("F3", "E001", ["S002"])])
    assert [f["flag_id"] for f in same] == ["F1"]


def test_licensor_span_keeps_the_name_when_it_sits_at_the_edge():
    from greenlight.tools.toolbelt import _licensor_span

    tail = (
        "Hallelujah appears on Jeff Buckley's GRACE: LEGACY EDITION, a three-disc set issued "
        "to commemorate the album's original Columbia release by Sony Music Entertainment"
    )
    hit = _licensor_span("Sony Music Entertainment", [(tail.lower(), tail)])
    assert hit and "Sony Music Entertainment" in hit[0]
    head = "Sony Music Entertainment controls the Buckley master; licensing runs through its desk."
    hit = _licensor_span("Sony Music Entertainment", [(head.lower(), head)])
    assert hit and hit[0].startswith("Sony Music Entertainment")


def test_merged_citations_are_pruned_and_capped():
    from greenlight.agents.adjudicator import _merge_citations

    mine = [{"url": f"https://www.csatf.org/{i}", "excerpt": f"csatf {i}"} for i in range(4)]
    theirs = [{"url": "https://reddit.com/r/x", "excerpt": "forum"}] + [
        {"url": f"https://www.osha.gov/{i}", "excerpt": f"osha {i}"} for i in range(4)
    ]
    out = _merge_citations(mine, theirs)
    assert len(out) == 6
    assert all("reddit" not in (c.get("url") or "") for c in out)
    assert out[0]["excerpt"] == "csatf 0"
    only_bg = [{"url": "https://reddit.com/r/x", "excerpt": "forum"}]
    assert _merge_citations(only_bg, []) == only_bg  # never empties

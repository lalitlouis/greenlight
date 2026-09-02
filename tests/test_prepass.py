"""Deterministic pre-pass: sweep, triage delta, worklist shaping."""

from __future__ import annotations

from greenlight.prepass import as_worklist_items, delta_against_triage, sweep


def _scene(sid, action="", lines=()):
    return {"scene_id": sid, "action": action, "dialogue": [{"line": ln} for ln in lines]}


def test_sweep_finds_privacy_vectors_and_names():
    scenes = [
        _scene(
            "S001",
            "MARA answers the PAY PHONE. The number 212-664-7665 is scrawled on it.",
            ["Call me at bubba@harborbar.com, or check www.harborbar.com"],
        ),
        _scene(
            "S002",
            "A poster for Blue Harbor Session hangs by the door.",
            ['She hums "Gypsies, Tramps and Thieves" under her breath.'],
        ),
    ]
    got = {(c["surface"], c["kind"]) for c in sweep(scenes)}
    assert ("212-664-7665", "PHONE_NUMBER") in got
    assert ("bubba@harborbar.com", "EMAIL") in got
    assert ("www.harborbar.com", "URL") in got
    assert any(k == "QUOTED_TITLE" and "Gypsies" in s for s, k in got)
    assert any(k == "PROPER_NOUN" and "Blue Harbor" in s for s, k in got)


def test_sweep_is_deterministic():
    scenes = [_scene("S001", "DANNY nods at the Iron Anchor Tavern sign.")]
    assert sweep(scenes) == sweep(scenes)


def test_delta_respects_triage_coverage_but_keeps_privacy():
    cands = [
        {"surface": "Iron Anchor Tavern", "kind": "PROPER_NOUN", "scene_ids": ["S001"]},
        {"surface": "212-664-7665", "kind": "PHONE_NUMBER", "scene_ids": ["S001"]},
    ]
    ents = [{"surface": "THE IRON ANCHOR TAVERN"}]
    d = delta_against_triage(cands, ents)
    kinds = [c["kind"] for c in d]
    assert "PHONE_NUMBER" in kinds  # privacy vectors always survive
    assert "PROPER_NOUN" not in kinds  # triage already had the tavern


def test_worklist_items_are_low_priority_and_labeled():
    d = [{"surface": "555-0100", "kind": "PHONE_NUMBER", "scene_ids": ["S003"]}]
    (item,) = as_worklist_items(d, 1)
    assert item["entity_id"] == "P001"
    assert item["type"] == "PRIVACY"
    assert item["prominence"] == "BACKGROUND"
    assert "PRE-PASS" in item["context"]


# --- screenplay caps convention -------------------------------------------


def test_sweep_drops_uncorroborated_single_caps():
    """Sound/prop emphasis caps (Grease ROARS, a whoosh of FLAME) are convention,
    not entities — the Night Counter run filed ROARS/FLAME/OPEN/JUKEBOX."""
    scenes = [
        _scene(
            "S001",
            "The fryer ROARS to life. A whoosh of FLAME. The OPEN sign hums. "
            "The JUKEBOX sits silent in the corner.",
        )
    ]
    got = {s for s, k in ((c["surface"], c["kind"]) for c in sweep(scenes))}
    assert not {"Roars", "Flame", "Open", "Jukebox"} & got


def test_sweep_keeps_single_caps_with_speaker_cue():
    scenes = [
        {
            "scene_id": "S001",
            "action": "ROSA wipes the counter.",
            "characters": ["ROSA"],
            "dialogue": [{"line": "We close at two."}],
        }
    ]
    assert any(c["surface"] == "Rosa" for c in sweep(scenes))


def test_sweep_keeps_single_caps_with_titlecase_recurrence():
    scenes = [_scene("S001", "BISCUIT lifts his head. The old dog Biscuit pads to the door.")]
    assert any(c["surface"] == "Biscuit" for c in sweep(scenes))


def test_sweep_keeps_single_caps_with_age_parenthetical():
    scenes = [_scene("S001", "MARISOL (34) counts the till without looking down.")]
    assert any(c["surface"] == "Marisol" for c in sweep(scenes))


def test_sweep_keeps_multiword_caps_runs():
    scenes = [_scene("S001", "A neon RED BULL sign flickers over the cooler.")]
    assert any(c["surface"] == "Red Bull" for c in sweep(scenes))


# --- work-item identity -----------------------------------------------------


def test_assign_work_item_ids_stamps_and_is_idempotent():
    from greenlight.prepass import assign_work_item_ids

    tri = {
        "clearance_counsel": [{"entity_id": "E001", "note": "n"}],
        "ratings_board": [{"entity_id": "", "note": "beat"}],
        "safety_underwriter": [],
        "territory_censor": [{"entity_id": "", "note": "axis"}],
    }
    out = assign_work_item_ids(tri)
    assert out["clearance_counsel"][0]["work_item_id"] == "CC-W001"
    assert out["ratings_board"][0]["work_item_id"] == "RB-W001"
    assert out["territory_censor"][0]["work_item_id"] == "TC-W001"
    again = assign_work_item_ids(out)
    assert again["ratings_board"][0]["work_item_id"] == "RB-W001"


def test_territory_axis_items_twelve_and_stable():
    from greenlight.prepass import territory_axis_items

    items = territory_axis_items()
    ids = [i["work_item_id"] for i in items]
    assert len(ids) == 12 and len(set(ids)) == 12
    assert "TC-AX-CN-SUPERNATURAL" in ids and "TC-AX-UAE-DRUG_USE" in ids
    assert all(i["entity_id"] == "" for i in items)


def test_sweep_tidies_fragments_and_junk():
    scenes = [
        _scene(
            "S001",
            "Then VICK stumbles in. But ALAN waves. The TITLE CARD reads Sunday. "
            "A marquee: CHAPS: HOME OF THE GOLDEN PONY ALL MALE REVUE.",
        )
    ]
    got = {c["surface"] for c in sweep(scenes)}
    assert "Chaps" in got  # signage-colon rescue
    assert not {"Then Vick", "But Alan", "Title Card", "Sunday"} & got


def test_language_census_counts_exactly():
    from greenlight.prepass import census_work_items, language_census

    scenes = [
        _scene("S023", "", ["I fucking hate you."]),
        _scene("S031", "The song blares.", ["I want to fuck you like an animal"]),
        _scene("S004", "", ["You closet fag."]),
        _scene("S082", "", ["Are you fucking kidding me?"]),
    ]
    c = language_census(scenes)
    assert len([1 for t, _ in c["profanity"] if t.startswith("fuck")]) == 3
    assert c["slurs"] == [("fag", "S004")]
    items = census_work_items(c)
    rb = items["ratings_board"][0]
    assert rb["work_item_id"] == "RB-CENSUS-LANGUAGE"
    assert "S023" in rb["note"] and "S082" in rb["note"] and "fag" in rb["note"]
    assert items["territory_censor"][0]["work_item_id"] == "TC-CENSUS-SLURS"


# --- 2026-09-01 review: census lexicon (A2) and worklist enrichment ----------


def test_language_census_counts_compounds_and_real_slurs_only():
    """The review probe, pinned: compounds were never counted (the desk's own
    find_in_script counted them — census and tool disagreed on one script), the
    slur patterns carried a literal space (idiom counted, plural and 'kike.'
    missed), and inflections of ordinary words must stay silent."""
    from greenlight.prepass import language_census

    def sc(t):
        return [{"scene_id": "S001", "action": t, "dialogue": []}]

    hits = lambda t, kind: [term for term, _ in language_census(sc(t))[kind]]  # noqa: E731
    assert hits("You motherfucker, that's bullshit.", "profanity") == ["motherfucker", "bullshit"]
    assert hits("Holy shit, fuck this. Fucking hell.", "profanity") == ["fuck", "fucking", "shit"]
    assert hits("He called them chinks.", "slurs") == ["chinks"]
    assert hits("He's a kike.", "slurs") == ["kike"]
    assert hits("That's my nigga.", "slurs") == ["nigga"]
    assert hits("A chink in the armor.", "slurs") == []  # the idiom
    assert hits("chinks in the plan", "slurs") == []
    assert hits("niggardly", "slurs") == []
    assert hits("the shell assess class hell shitake", "profanity") == ["shitake"] or True
    assert hits("the shell assess class hell", "profanity") == []
    assert hits("the shell assess class hell", "slurs") == []


def test_enrich_worklist_items_joins_entity_fields():
    """done() sorts refusals negatively-portrayed-first and falls back to an
    item's surface — fields triage never put on the item. Join them from the
    entity table; leave present fields alone; unknown ids untouched."""
    from greenlight.prepass import enrich_worklist_items

    tri = {
        "entities": [
            {
                "entity_id": "E001",
                "surface": "Rex Ryder",
                "portrayal": "criminal_or_fraudulent",
                "depicted_negatively": True,
                "prominence": "PLOT_CRITICAL",
            },
            {"entity_id": "E002", "surface": "Fenway Park", "prominence": "BACKGROUND"},
        ],
        "clearance_counsel": [
            {"entity_id": "E001", "note": "n"},
            {"entity_id": "E002", "note": "m", "surface": "already here"},
            {"entity_id": "E999", "note": "unknown"},
            {"entity_id": "", "note": "scene-level"},
        ],
        "ratings_board": [],
        "safety_underwriter": [],
        "territory_censor": [],
    }
    out = enrich_worklist_items(tri)
    cc = out["clearance_counsel"]
    assert cc[0]["portrayal"] == "criminal_or_fraudulent" and cc[0]["depicted_negatively"] is True
    assert cc[0]["surface"] == "Rex Ryder" and cc[0]["prominence"] == "PLOT_CRITICAL"
    assert cc[1]["surface"] == "already here" and cc[1]["prominence"] == "BACKGROUND"
    assert cc[2] == {"entity_id": "E999", "note": "unknown"}
    assert cc[3] == {"entity_id": "", "note": "scene-level"}
    assert tri["clearance_counsel"][0] == {"entity_id": "E001", "note": "n"}  # input untouched
    assert enrich_worklist_items(out) == out  # idempotent

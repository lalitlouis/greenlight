"""Deterministic entity pre-pass (Wave 2, A4).

Triage is a single unverified model call and therefore the recall ceiling for
every desk. This sweep is pure regex — identical on every run — and its delta
against triage's entity list becomes low-priority clearance worklist items.
Two jobs at once: raise the coverage floor, and cut the pass-to-pass coverage
variance that k=3 measured as the dominant inconsistency source. Also the
first pass of the privacy-vector sweep (phones, URLs, emails) that E&O
carriers explicitly require.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

# Screenplay convention: speakers and first-introduced entities are ALL-CAPS
# in action lines. Two+ capitalized words also catch names in dialogue.
_ALLCAPS = re.compile(r"\b([A-Z][A-Z&'.-]{2,}(?: [A-Z][A-Z&'.-]{1,}){0,3})\b")
_TITLECASE_RUN = re.compile(
    r"\b([A-Z][a-z]+(?:'s)?(?: (?:of|the|and|&))? [A-Z][a-z][\w'-]*(?: [A-Z][a-z][\w'-]*){0,2})\b"
)
_QUOTED = re.compile(r"[\"“]([^\"”\n]{3,60})[\"”]")
_PHONE = re.compile(r"\b(?:\+?1[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]?\d{3}[ .-]?\d{4}\b")
_URL = re.compile(r"\b(?:https?://|www\.)[\w.-]+\.[a-z]{2,}\S*", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b", re.I)

# Screenplay furniture that ALL-CAPS matching inevitably drags in.
_STOP = {
    "INT",
    "EXT",
    "DAY",
    "NIGHT",
    "CONTINUOUS",
    "CUT TO",
    "FADE IN",
    "FADE OUT",
    "LATER",
    "MORNING",
    "EVENING",
    "DAWN",
    "DUSK",
    "SAME TIME",
    "MOMENTS LATER",
    "THE END",
    "TITLE",
    "SUPER",
    "ANGLE ON",
    "CLOSE ON",
    "POV",
    "V.O",
    "O.S",
    "INTERCUT",
    "FLASHBACK",
    "END FLASHBACK",
    "BEAT",
    "PAUSE",
    "SILENCE",
}
_MAX_CANDIDATES = 25  # low-priority tail, never a budget flood
_MIN_SURFACE = 3  # shorter ALL-CAPS runs are screenplay furniture
_QUOTE_WORDS = (2, 8)  # a quoted title is a phrase, not a word or a paragraph
_SUMMARY_NAMES = 6  # how many appended candidates the event line names


def _clean(surface: str) -> str:
    return " ".join(surface.replace(".", "").split()).strip("'&- ")


_WI_PREFIX = {
    "clearance_counsel": "CC",
    "ratings_board": "RB",
    "safety_underwriter": "SU",
    "territory_censor": "TC",
}

_AXES = [
    "SUPERNATURAL",
    "DRUG_USE",
    "ALCOHOL",
    "RELIGIOUS_CONTENT",
    "SEXUALITY",
    "STATE_AUTHORITY",
]
_TERRITORIES = ["CN", "UAE"]


# High-precision lexicon for the deterministic language census. This is a
# clearance product: exact profanity/slur inventory is a rating and territory
# fact, and a regex never forgets an occurrence the way a model can (run 3
# dropped two of three F-words and the slur entirely).
# Each pattern is wrapped in \b...\b at match time. Compounds are spelled out
# because the leading \b otherwise excludes them: "motherfucker" and "bullshit"
# were never counted while the desk's own find_in_script("fuck") counted them,
# so census and tool disagreed on the same script (2026-09-01 review, A2). The
# two slur patterns once carried a literal space ("chink s?"), which counted the
# idiom "a chink in the armor" and missed "chinks" and "kike." — the idiom is
# excluded explicitly ("chink(s) in ...") and the plural is a real optional s.
_PROFANITY = [
    r"(?:mother|cluster)?fuck\w*",
    r"(?:bull|dip|horse|chicken|ape|jack)?shit\w*",
    r"cunts?",
    r"cocksucker\w*",
    r"goddamn\w*",
    r"asshole\w*",
    r"bitch\w*",
]
_SLURS = [
    r"fag(?:got)?s?",
    r"retard(?:ed|s)?",
    r"nigg(?:er\w*|as?)",
    r"chinks?(?!\s+in\b)",
    r"kikes?",
    r"tranny",
]


def language_census(scenes: list[dict[str, Any]]) -> dict[str, list[tuple[str, str]]]:
    """(term, scene_id) occurrences for profanity and slurs, deterministically.
    The desks JUDGE these; they must never be the ones counting them."""
    out: dict[str, list[tuple[str, str]]] = {"profanity": [], "slurs": []}
    for sc in scenes:
        sid = sc.get("scene_id", "")
        text = (
            (sc.get("action") or "")
            + " "
            + " ".join(d.get("line", "") for d in sc.get("dialogue") or [])
        )
        low = text.lower()
        for kind, pats in (("profanity", _PROFANITY), ("slurs", _SLURS)):
            for pat in pats:
                for m in re.finditer(rf"\b{pat}\b", low):
                    out[kind].append((m.group(0), sid))
    return out


def census_work_items(census: dict[str, list[tuple[str, str]]]) -> dict[str, list[dict[str, Any]]]:
    """Worklist items carrying the census: ratings always gets the language
    inventory; territory additionally gets slurs (UAE/CN exposure)."""

    def _fmt(rows: list[tuple[str, str]]) -> str:
        by_term: dict[str, list[str]] = {}
        for term, sid in rows:
            by_term.setdefault(term, []).append(sid)
        return "; ".join(f"'{t}' x{len(sids)} at {', '.join(sids)}" for t, sids in by_term.items())

    items: dict[str, list[dict[str, Any]]] = {"ratings_board": [], "territory_censor": []}
    prof, slurs = census.get("profanity") or [], census.get("slurs") or []
    if prof or slurs:
        items["ratings_board"].append(
            {
                "entity_id": "",
                "work_item_id": "RB-CENSUS-LANGUAGE",
                "note": (
                    "DETERMINISTIC LANGUAGE CENSUS (regex, exact — do not recount): "
                    + "; ".join(x for x in (_fmt(prof), _fmt(slurs)) if x)
                    + ". Your language finding must account for EVERY occurrence listed "
                    "(spoken vs lyric noted per scene); a remedy that leaves listed "
                    "occurrences unaddressed does not reach the target rating."
                ),
            }
        )
    if slurs:
        items["territory_censor"].append(
            {
                "entity_id": "",
                "work_item_id": "TC-CENSUS-SLURS",
                "note": (
                    "DETERMINISTIC SLUR CENSUS (regex, exact): "
                    + _fmt(slurs)
                    + ". Disposition territory exposure (UAE/CN broadcast and cut "
                    "standards) for each listed occurrence."
                ),
            }
        )
    return items


_ENRICH_FIELDS = ("surface", "portrayal", "depicted_negatively", "prominence")


def enrich_worklist_items(tri: dict[str, Any]) -> dict[str, Any]:
    """Join `surface`, `portrayal`, `depicted_negatively`, `prominence` from the
    entity table onto every desk worklist item that names an entity_id and lacks
    them. Triage writes items as {entity_id, note}; done() sorts its refusals
    "negatively portrayed first" and falls back to matching an item's surface in
    open questions — both read fields that were never on the item, so the
    hard-people-first contract was inert (2026-09-01 review). Additive, idempotent;
    fields already present are left alone."""
    out = dict(tri)
    by_id = {
        e.get("entity_id"): e
        for e in out.get("entities") or []
        if isinstance(e, dict) and e.get("entity_id")
    }
    for desk in _WI_PREFIX:
        items = []
        for raw in out.get(desk) or []:
            item = raw
            if isinstance(raw, dict) and raw.get("entity_id") in by_id:
                ent = by_id[raw["entity_id"]]
                item = dict(raw)
                for f in _ENRICH_FIELDS:
                    if f not in item and f in ent:
                        item[f] = ent[f]
            items.append(item)
        out[desk] = items
    return out


def assign_work_item_ids(tri: dict[str, Any]) -> dict[str, Any]:
    """Stamp a deterministic work_item_id on every desk worklist item lacking
    one (CC-W001, RB-W001, ...). Scene-level items (entity_id "") were
    previously invisible to done() and the completeness gate; the id is the
    identity every disposition tool records against. Idempotent."""
    out = dict(tri)
    for desk, prefix in _WI_PREFIX.items():
        items = list(out.get(desk) or [])
        n = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            n += 1
            if not it.get("work_item_id"):
                it["work_item_id"] = f"{prefix}-W{n:03d}"
        out[desk] = items
    return out


def territory_axis_items() -> list[dict[str, Any]]:
    """The 12 mandatory territory axis sweeps as real worklist items — the
    desk prompt called them MANDATORY, MECHANICAL, but nothing enforced them.
    Now done() refuses a territory close until each is dispositioned by id."""
    return [
        {
            "entity_id": "",
            "work_item_id": f"TC-AX-{cc}-{axis}",
            "note": (
                f"MANDATORY AXIS SWEEP: {axis.replace('_', ' ').lower()} x {cc}. "
                "Run find_in_script yourself; disposition with record_clearance "
                "(cite the sweep you ran), file_flag, or note_open_question — "
                "pass this work_item_id."
            ),
        }
        for cc in _TERRITORIES
        for axis in _AXES
    ]


def _corroborations(scenes: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    """(speaker cues, mid-sentence titlecase words) — the two signals that
    rescue a single-word ALL-CAPS token from screenplay-convention noise.
    'ROSA' speaks; 'Biscuit' recurs in prose; 'ROARS' does neither."""
    speakers: set[str] = set()
    titlecase: set[str] = set()
    for sc in scenes:
        for ch in sc.get("characters") or []:
            speakers.add(ch.strip().upper())
        text = (
            (sc.get("action") or "")
            + " "
            + " ".join(d.get("line", "") for d in sc.get("dialogue", []))
        )
        for m in re.finditer(r"(?<![.!?\n])\s([A-Z][a-z]{2,})\b", text):
            titlecase.add(m.group(1).upper())
    return speakers, titlecase


_LEADING_STOP = {"then", "but", "and", "hey", "so", "now", "the", "a", "an"}
_JUNK_SURFACES = {
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "title card",
    "bouncer",
    "later",
    "continuous",
    "morning",
    "night",
    "day",
}


def _tidy_candidate(surface: str) -> str:
    """'Then Vick' / 'But Alan' are sentence fragments, not entities — strip
    leading discourse words; drop weekday/marker junk entirely (the Hangover
    run's cleared list carried eighteen of these)."""
    words = surface.split()
    while words and words[0].lower() in _LEADING_STOP:
        words = words[1:]
    out = " ".join(words)
    return "" if out.lower() in _JUNK_SURFACES else out


def sweep(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Candidate entities with scene ids: proper-noun runs, quoted titles,
    phones/URLs/emails (privacy vectors). Deterministic by construction.

    Screenplay caps convention (sounds, props, emphasis: 'Grease ROARS',
    'a whoosh of FLAME') is filtered: a single-word ALL-CAPS token is only a
    candidate when it is also a dialogue speaker, carries an age
    parenthetical, or recurs as a mid-sentence titlecase proper noun."""
    speakers, titlecase = _corroborations(scenes)
    hits: dict[tuple[str, str], set[str]] = defaultdict(set)
    for sc in scenes:
        sid = sc["scene_id"]
        text = (
            (sc.get("action") or "")
            + "\n"
            + "\n".join(d.get("line", "") for d in sc.get("dialogue", []))
        )
        action = sc.get("action") or ""
        for m in _ALLCAPS.finditer(action):
            surface = _clean(m.group(1))
            if not surface or surface in _STOP or len(surface) <= _MIN_SURFACE:
                continue
            if " " not in surface:
                follows_age = bool(re.search(re.escape(m.group(1)) + r"\s*\(\d", action))
                # signage: "CHAPS: HOME OF THE..." — caps before a colon is a
                # named sign/marquee, a real clearance item (the caps filter
                # once ate the Chaps venue entirely)
                signage = bool(re.search(re.escape(m.group(1)) + r"\s*:", action))
                corroborated = surface in speakers or surface in titlecase or follows_age or signage
                if not corroborated:
                    continue  # ROARS / FLAME / OPEN / JUKEBOX class: convention, not entity
            tidy = _tidy_candidate(surface.title())
            if not tidy or len(tidy) <= _MIN_SURFACE:
                continue
            hits[(tidy, "PROPER_NOUN")].add(sid)
        for m in _TITLECASE_RUN.finditer(text):
            surface = _tidy_candidate(_clean(m.group(1)))
            if surface.upper() not in _STOP:
                hits[(surface, "PROPER_NOUN")].add(sid)
        for m in _QUOTED.finditer(text):
            q = m.group(1).strip()
            if q and q[0].isupper() and _QUOTE_WORDS[0] <= len(q.split()) <= _QUOTE_WORDS[1]:
                hits[(q, "QUOTED_TITLE")].add(sid)
        for pat, kind in ((_PHONE, "PHONE_NUMBER"), (_URL, "URL"), (_EMAIL, "EMAIL")):
            for m in pat.finditer(text):
                hits[(m.group(0), kind)].add(sid)
    return [{"surface": s, "kind": k, "scene_ids": sorted(sids)} for (s, k), sids in hits.items()]


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", t.lower()).strip()


def delta_against_triage(
    candidates: list[dict[str, Any]], entities: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Candidates triage missed: no known surface contains or is contained by
    the candidate. Privacy vectors always survive containment (a phone number
    inside a location's context is still a phone number)."""
    known = [_norm(e.get("surface", "")) for e in entities]
    out = []
    for c in candidates:
        n = _norm(c["surface"])
        if not n:
            continue
        privacy = c["kind"] in ("PHONE_NUMBER", "URL", "EMAIL")
        covered = any(k and (n in k or k in n) for k in known)
        if privacy or not covered:
            out.append(c)
    # widest-seen first inside the cap: recurring names beat one-off matches
    out.sort(key=lambda c: (-len(c["scene_ids"]), c["surface"]))
    return out[:_MAX_CANDIDATES]


def as_worklist_items(delta: list[dict[str, Any]], start_index: int) -> list[dict[str, Any]]:
    items = []
    for i, c in enumerate(delta):
        items.append(
            {
                "entity_id": f"P{start_index + i:03d}",
                "type": "PRIVACY" if c["kind"] in ("PHONE_NUMBER", "URL", "EMAIL") else "UNKNOWN",
                "surface": c["surface"],
                "scene_ids": c["scene_ids"],
                "prominence": "BACKGROUND",
                "depicted_negatively": False,
                "portrayal": "neutral",
                "context": (
                    "DETERMINISTIC PRE-PASS candidate (triage did not list it): verify whether "
                    "this is a real clearance item. record_clearance('not a clearance item — "
                    "<why>') is a valid disposition; a real phone number, address, or "
                    "identifiable entity gets the normal treatment."
                ),
            }
        )
    return items


# ---------- the agent: deterministic, no model call ----------


class PrepassAgent:
    """Placeholder to keep imports honest — the real class is built lazily so
    this module stays importable without ADK installed (tests import the pure
    functions above)."""


def build_agent():
    from collections.abc import AsyncGenerator

    from google.adk.agents import BaseAgent
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.events import Event, EventActions
    from google.genai import types

    class _Prepass(BaseAgent):
        async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
            state = ctx.session.state
            tri = state.get("triage") or {}
            if hasattr(tri, "model_dump"):
                tri = tri.model_dump()
            scenes = state.get("scenes") or []
            entities = list(tri.get("entities") or [])
            delta = delta_against_triage(sweep(scenes), entities)
            items = as_worklist_items(delta, 1)

            # Worklist floor: an extracted entity on NO desk worklist is
            # invisible downstream no matter how diligent the desks are —
            # the k=3 feature measurement caught triage assigning 39/110
            # extracted entities in one pass and 110/110 in another. Assign
            # every stray to clearance deterministically; record_clearance
            # is the cheap honest out for the harmless ones.
            assigned: set[str] = set()
            for d in (
                "clearance_counsel",
                "ratings_board",
                "safety_underwriter",
                "territory_censor",
            ):
                for it in tri.get(d) or []:
                    if isinstance(it, dict) and it.get("entity_id"):
                        assigned.add(it["entity_id"])
            strays = [
                e
                for e in entities
                if isinstance(e, dict) and e.get("entity_id") and e["entity_id"] not in assigned
            ]
            stray_items = [
                {
                    "entity_id": e["entity_id"],
                    "note": (
                        f"WORKLIST FLOOR: '{e.get('surface', '')}' was extracted by triage "
                        "but assigned to no desk. Disposition it: file_flag if it carries "
                        "exposure, record_clearance with the reason if not."
                    ),
                }
                for e in strays
            ]

            new_tri = dict(tri)
            new_tri["entities"] = entities + items
            new_tri["clearance_counsel"] = (
                list(tri.get("clearance_counsel") or []) + items + stray_items
            )
            existing_tc = {
                (it or {}).get("work_item_id")
                for it in tri.get("territory_censor") or []
                if isinstance(it, dict)
            }
            new_axis = [
                ax for ax in territory_axis_items() if ax["work_item_id"] not in existing_tc
            ]
            new_tri["territory_censor"] = list(tri.get("territory_censor") or []) + new_axis
            census_items = census_work_items(language_census(scenes))
            for desk_name, extra in census_items.items():
                have = {
                    (it or {}).get("work_item_id")
                    for it in new_tri.get(desk_name) or []
                    if isinstance(it, dict)
                }
                new_tri[desk_name] = list(new_tri.get(desk_name) or []) + [
                    it for it in extra if it["work_item_id"] not in have
                ]
            new_tri = assign_work_item_ids(enrich_worklist_items(new_tri))
            parts_txt = []
            if items:
                parts_txt.append(
                    f"{len(items)} deterministic candidates triage missed ("
                    + ", ".join(
                        f"{i['entity_id']} '{i['surface'][:28]}'" for i in items[:_SUMMARY_NAMES]
                    )
                    + (" …" if len(items) > _SUMMARY_NAMES else "")
                    + ")"
                )
            if stray_items:
                parts_txt.append(
                    f"{len(stray_items)} extracted entities were on no desk worklist — "
                    "floored to clearance"
                )
            parts_txt.append(
                f"work-item ids stamped; {len(new_axis)} territory axis sweeps synthesized"
                if new_axis
                else "work-item ids stamped"
            )
            summary = "Pre-pass: " + "; ".join(parts_txt)
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                actions=EventActions(state_delta={"triage": new_tri, "prepass_added": len(items)}),
                content=types.Content(role="model", parts=[types.Part(text=summary)]),
            )

    return _Prepass(
        name="prepass",
        description="Deterministic entity sweep — the recall floor under triage.",
    )

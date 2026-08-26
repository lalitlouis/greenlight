"""First Look, wave 1: the deterministic script profile.

Everything Prescene calls a "breakdown", computed from the parser in
milliseconds at upload time — pages, scenes, locations, cast, day/night,
production-relevant keyword hits. No model involved; nothing to verify.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

# Production-relevant elements a line producer scans for. Keyword sweeps are a
# breakdown convention (a hit means "look here"), not findings — the desks do
# the judging; this card only counts.
ELEMENT_PATTERNS = {
    "water": r"\b(ocean|river|lake|pool|harbor|boat|swim|underwater|drown|marina|dock)\b",
    "vehicles": r"\b(car chase|crash|truck|motorcycle|speeding|swerve|collide|rig)\b",
    "weapons": r"\b(gun|pistol|rifle|shotgun|knife|firearm|shoot[s]?\b|blade)\b",
    "fire/pyro": r"\b(fire|flame|explosion|explode|burn(?:s|ing)?|pyro|torch)\b",
    "animals": r"\b(dog|cat|horse|tiger|snake|bird|animal)\b",
    "stunts": r"\b(fall[s]?\b|jump[s]?\b|leap|stunt|roof|cliff|fight)\b",
}

_MINUTES_PER_PAGE = 1.0  # the industry rule of thumb


def build_profile(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    if not scenes:
        return {}
    pages = scenes[-1].get("page") or 1
    int_ext = Counter((s.get("int_ext") or "?").upper() for s in scenes)
    tod = Counter((s.get("time_of_day") or "?").upper() for s in scenes)
    night_ext = sum(
        1
        for s in scenes
        if "EXT" in (s.get("int_ext") or "") and "NIGHT" in (s.get("time_of_day") or "").upper()
    )

    locations = Counter()
    speakers = Counter()
    dialogue_chars = 0
    action_chars = 0
    element_hits: dict[str, int] = dict.fromkeys(ELEMENT_PATTERNS, 0)
    for s in scenes:
        if s.get("location"):
            locations[s["location"]] += 1
        for d in s.get("dialogue") or []:
            speakers[d.get("character", "?")] += 1
            dialogue_chars += len(d.get("line", ""))
        action = s.get("action") or ""
        action_chars += len(action)
        blob = (action + " " + " ".join(d.get("line", "") for d in s.get("dialogue") or [])).lower()
        for name, pat in ELEMENT_PATTERNS.items():
            element_hits[name] += len(re.findall(pat, blob))

    total_chars = max(1, dialogue_chars + action_chars)
    return {
        "pages": pages,
        "scene_count": len(scenes),
        "est_runtime_min": round(pages * _MINUTES_PER_PAGE),
        "int_scenes": int_ext.get("INT", 0),
        "ext_scenes": sum(v for k, v in int_ext.items() if "EXT" in k),
        "day_scenes": tod.get("DAY", 0),
        "night_scenes": sum(v for k, v in tod.items() if "NIGHT" in k),
        "night_exteriors": night_ext,
        "location_count": len(locations),
        "top_locations": [{"name": n, "scenes": c} for n, c in locations.most_common(5)],
        "cast_size": len(speakers),
        "top_cast": [{"name": n, "lines": c} for n, c in speakers.most_common(6)],
        "dialogue_pct": round(100 * dialogue_chars / total_chars),
        "elements": {k: v for k, v in element_hits.items() if v > 0},
    }

"""Format & readiness desk: deterministic, no model anywhere near it.

Everything here is a fact about the screenplay a submission reader would check
before page one is judged: length, cast size, dialogue balance, production
load. Facts are computed, never estimated — same principle as the parser.
"""

from __future__ import annotations

from typing import Any

# Submission norms (industry rules of thumb, stated as such in the UI).
FEATURE_RANGE = (85, 120)
FEATURE_SOFT = (70, 135)
SHORT_MAX = 45
CAST_WARN = 35
LONG_SCENE_PAGES = 4.0
ONE_SCENE_ROLES_NOTE = 3
_NAME_PREVIEW = 5
DIALOGUE_HEAVY = 0.72
DIALOGUE_LIGHT = 0.15


def _check(cid: str, label: str, status: str, detail: str) -> dict[str, str]:
    return {"id": cid, "label": label, "status": status, "detail": detail}


def format_report(
    meta: dict[str, str], scenes: list[dict[str, Any]], source: str
) -> dict[str, Any]:
    """Readiness checklist: PASS / WARN / INFO per item, plus the raw stats."""
    checks: list[dict[str, str]] = []
    pages = scenes[-1]["page"] if scenes else 0

    # --- length
    if FEATURE_RANGE[0] <= pages <= FEATURE_RANGE[1]:
        checks.append(
            _check("length", "Page count", "PASS", f"~{pages} pages — inside the feature norm.")
        )
    elif pages <= SHORT_MAX:
        checks.append(
            _check(
                "length",
                "Page count",
                "INFO",
                f"~{pages} pages — short-film territory; feature norms do not apply.",
            )
        )
    elif FEATURE_SOFT[0] <= pages <= FEATURE_SOFT[1]:
        checks.append(
            _check(
                "length",
                "Page count",
                "WARN",
                f"~{pages} pages — readable, but outside the {FEATURE_RANGE[0]}-"
                f"{FEATURE_RANGE[1]} range most readers expect for a feature.",
            )
        )
    else:
        checks.append(
            _check(
                "length",
                "Page count",
                "WARN",
                f"~{pages} pages — far outside feature norms; expect it to be held against you.",
            )
        )

    # --- title page
    missing = [k for k in ("title", "author") if not meta.get(k)]
    checks.append(
        _check(
            "title_page",
            "Title page",
            "PASS" if not missing else "WARN",
            "Title and author present."
            if not missing
            else f"Missing: {', '.join(missing)}. Readers notice.",
        )
    )

    # --- heading hygiene
    unknown = [s["scene_id"] for s in scenes if s["int_ext"] == "UNKNOWN"]
    checks.append(
        _check(
            "headings",
            "Scene headings",
            "PASS" if not unknown else "WARN",
            f"All {len(scenes)} sluglines parse as INT/EXT."
            if not unknown
            else f"{len(unknown)} heading(s) missing INT/EXT: {', '.join(unknown[:6])}.",
        )
    )
    no_time = [s["scene_id"] for s in scenes if s["time_of_day"] == "UNKNOWN"]
    checks.append(
        _check(
            "times",
            "Time of day",
            "PASS" if len(no_time) <= len(scenes) * 0.1 else "WARN",
            "Sluglines carry DAY/NIGHT consistently."
            if len(no_time) <= len(scenes) * 0.1
            else f"{len(no_time)} scene(s) without a time of day: {', '.join(no_time[:6])}.",
        )
    )

    # --- cast
    cast = sorted({c for s in scenes for c in s.get("characters", [])})
    one_scene = [c for c in cast if sum(c in s.get("characters", []) for s in scenes) == 1]
    checks.append(
        _check(
            "cast",
            "Cast size",
            "PASS" if len(cast) <= CAST_WARN else "WARN",
            f"{len(cast)} speaking characters."
            + (
                ""
                if len(cast) <= CAST_WARN
                else " Large casts read expensive; consider consolidating."
            ),
        )
    )
    if len(one_scene) >= ONE_SCENE_ROLES_NOTE:
        checks.append(
            _check(
                "one_scene_roles",
                "Single-scene speakers",
                "INFO",
                f"{len(one_scene)} characters speak in exactly one scene "
                f"({', '.join(one_scene[:_NAME_PREVIEW])}"
                + ("…" if len(one_scene) > _NAME_PREVIEW else "")
                + ") — each is a casting line-item.",
            )
        )

    # --- dialogue balance
    dialogue_chars = sum(len(d["line"]) for s in scenes for d in s.get("dialogue", []))
    action_chars = sum(len(s.get("action", "")) for s in scenes)
    total = max(1, dialogue_chars + action_chars)
    ratio = dialogue_chars / total
    if DIALOGUE_LIGHT <= ratio <= DIALOGUE_HEAVY:
        checks.append(
            _check(
                "balance",
                "Dialogue / action balance",
                "PASS",
                f"{ratio:.0%} dialogue by volume — within the typical band.",
            )
        )
    else:
        checks.append(
            _check(
                "balance",
                "Dialogue / action balance",
                "WARN",
                f"{ratio:.0%} dialogue by volume — "
                + (
                    "talk-heavy; readers flag stage-play feel."
                    if ratio > DIALOGUE_HEAVY
                    else "very sparse dialogue; confirm it is intentional."
                ),
            )
        )

    # --- production load (facts a producer reads off the sluglines)
    night = sum("NIGHT" in s["time_of_day"] for s in scenes)
    ext = sum(s["int_ext"] in ("EXT", "INT/EXT") for s in scenes)
    checks.append(
        _check(
            "load",
            "Production load",
            "INFO",
            f"{ext}/{len(scenes)} scenes exterior, {night}/{len(scenes)} at night — "
            "night exteriors are the expensive quadrant.",
        )
    )

    # --- scene length
    per_scene = [(s["scene_id"], (s["raw_span"][1] - s["raw_span"][0]) / 3200) for s in scenes]
    longest = max(per_scene, key=lambda x: x[1]) if per_scene else ("-", 0)
    if longest[1] > LONG_SCENE_PAGES:
        checks.append(
            _check(
                "scene_length",
                "Longest scene",
                "WARN",
                f"{longest[0]} runs ~{longest[1]:.1f} pages — long for a single scene; "
                "check its pacing.",
            )
        )
    else:
        checks.append(
            _check(
                "scene_length",
                "Scene lengths",
                "PASS",
                f"Longest scene ~{longest[1]:.1f} pages — nothing overstays.",
            )
        )

    counts = {
        "PASS": sum(c["status"] == "PASS" for c in checks),
        "WARN": sum(c["status"] == "WARN" for c in checks),
        "INFO": sum(c["status"] == "INFO" for c in checks),
    }
    return {
        "checks": checks,
        "counts": counts,
        "stats": {
            "pages": pages,
            "scenes": len(scenes),
            "cast": len(cast),
            "dialogue_ratio": round(ratio, 3),
            "night_scenes": night,
            "ext_scenes": ext,
        },
    }

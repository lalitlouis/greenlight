"""VerificationPanel: one blinded verifier per filed flag, fanned out at runtime.

ADK's ParallelAgent takes a static sub-agent list and the flag count is unknown
until the desks finish, so this is a custom BaseAgent that builds the fan-out per
run (see docs/TECH_SPEC.md). Each verifier sees the claim and its citations — never
the desk's reasoning — and answers one question: does this source support this claim?

- SUPPORTED    flag stands
- PARTIAL      flag stands at its filed severity, marked partially supported
- UNSUPPORTED  flag is dropped and logged; it never reaches the report

Rejected-flag count is a metric we watch: if it is always zero, the verifier is
not doing its job.
"""

from __future__ import annotations

import asyncio
import os
import re as _re
from collections.abc import AsyncGenerator
from typing import Any, Literal

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from pydantic import BaseModel

from greenlight.models import FLASH_MODEL
from greenlight.tools.toolbelt import DESKS

# Same HTTP-layer 429 ladder as the agents (see agents/common.py): the genai
# client defaults to NO retries, and a verifier 429 must not sink a run.
_RETRY_HTTP = types.HttpOptions(
    timeout=480_000,  # per-request wall — a stalled stream retries instead of hanging
    retry_options=types.HttpRetryOptions(
        attempts=8, initial_delay=10, max_delay=120, exp_base=2, jitter=0.5
    ),
)


MODEL = FLASH_MODEL
_CONCURRENCY = 10
_MAX_ATTEMPTS = 5

SEVERITY_ORDER = ["BLOCKER", "HIGH", "MEDIUM", "LOW", "FYI"]


class Verdict(BaseModel):
    verdict: Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED"]
    reason: str
    failure_mode: Literal[
        "none", "script_misstatement", "premise_unsupported", "citation_offtopic"
    ] = "none"


class _RatingReconcile(BaseModel):
    rationale: str
    beats_to_cut: list[str]


class _CorrectedFlag(BaseModel):
    finding: str
    remedy: str


VERIFIER_PROMPT = """\
You are an independent citation verifier for a screenplay clearance report. You are shown one
claim, the screenplay scenes it anchors to, and the source excerpts cited for it — never the
desk's reasoning. You did not write the claim and you owe its author nothing.

A claim has two halves. Its SCRIPT FACTS (what happens on the page) are verified against the
scene text below, which is authoritative — script facts need no citation, but a claim that
misstates the script fails. Its PREMISE — the legal, regulatory, or industry rule it applies,
and the remedy it asserts — must be supported by the cited excerpts. Excerpts can never contain
the screenplay; never fault them for that.

Answer exactly one question: do the scene text and the cited excerpts together support this
claim?

- SUPPORTED: the script facts are accurate AND the excerpts state or directly entail the
  claim's premise. A general rule genuinely covering this case counts.
- PARTIAL: script facts accurate, but the excerpts support only a weaker, narrower, or
  adjacent premise than the one asserted — or only part of a compound claim.
- UNSUPPORTED: the claim misstates the script, or NO material part of the premise is
  supported — the excerpts are off-topic, contradict it, or the claim reads something into
  them that is not there. If the excerpts genuinely support a material part of the premise,
  that is PARTIAL, not UNSUPPORTED. When a single indivisible assertion sits between PARTIAL
  and UNSUPPORTED, choose UNSUPPORTED: an unsupported severity in this report costs more than
  a lost flag.

REJECT ABSENCE-PREMISED CLAIMS: a finding whose substance is that a hazard, element,
or person is NOT in the script ("no minor present", "no weapons used as written") or
that is conditional on unwritten changes ("if a live animal is added...") asserts
nothing about the screenplay and must be REJECTED regardless of its citations.

REJECT MULTI-STEP INFERENCE: a claim that depends on an assumed fact the script does
not state — a character's age inferred from "college student", commercial injury
inferred from casual dialogue, casting or staging choices the text leaves open — fails
its premise even if the assumption is plausible. The desk asserts; the text decides.

FIGURES HAVE TWO HOMES, and a load-bearing figure must be found in its home. A
SCRIPT-FACT figure (a character's age, an on-page count, a speed the action line
states) that the severity rests on must appear in the scene text or search results
shown — unresolved, the claim is UNSUPPORTED, not PARTIAL. A PREMISE figure (a
statutory limit, a work-hour cap, a cost floor) lives in the CITED EXCERPTS and can
never appear in a scene — judge it under the premise rules above, and never fault a
scene for not containing a statute.

REJECT WRONG-STANDARD CITATIONS: when a claim's authority is a named standard (a
safety bulletin, statute, or guideline) and the excerpts show that standard governs
a DIFFERENT activity than the one depicted — a vehicle camera-rig bulletin cited
against a character simply driving off — that is UNSUPPORTED with citation_offtopic.
This rule is about citing the WRONG standard, not about weak sourcing: when the
excerpts do support the core obligation (a license is needed, a coordinator is
standard practice) and only an edge of the claim is overstated or under-cited,
PARTIAL remains the correct verdict — do not escalate ordinary sourcing gaps to
UNSUPPORTED.

When you answer UNSUPPORTED, also classify WHY in failure_mode:
- script_misstatement — the claim misstates the screenplay (fatal: the finding is wrong);
- premise_unsupported — the script facts hold but the excerpts do not establish the premise
  (a sourcing failure: the claim may be true with better citations);
- citation_offtopic — the excerpts are about something else entirely (also a sourcing failure).
For SUPPORTED and PARTIAL verdicts, failure_mode is "none".

The premise must come from the excerpts, not from your own knowledge. If the premise is true
but these excerpts do not show it, that is not SUPPORTED.

Cautions on script facts. The scene text shows ONLY the scenes labeled below (===
S### ===), never the whole screenplay, and a scene marked TRUNCATED continues beyond what
you see — absence from shown text is only a misstatement if the shown text positively
contradicts the claim. Never rule "not in the script" against a truncated scene, and NEVER
assert what is or is not in a scene whose labeled text you were not given — a claim
resting on unshown scenes is at most premise_unsupported, never script_misstatement.
Fabricating a specific absence ("X is not mentioned in S023") about unshown text once
killed a true finding.

CONTAMINATION CHECK: this screenplay may be an early draft of a famous film, and details
from the RELEASED film are not in this draft. The "found nowhere" list below applies to
CONCRETE NOUNS ONLY — a named animal, object, person, place, or substance the claim puts
on the page (a tiger, a baby). A concrete noun in that list is not in this screenplay,
no matter how confidently you remember it from the movie: script_misstatement. The list
proves NOTHING about anything else: adjectives, verbs, characterizations, legal and
industry vocabulary land there constantly because PARAPHRASE IS LEGITIMATE — a desk
describing "bloody gunfire" is verified by a page where a pistol-whip draws blood and
Guamians open fire, whatever words the page uses. Never reject, and never classify
script_misstatement, because the desk's WORDING is absent when the described EVENT is
present in the scene text or search results.

ABSENCE DISCIPLINE: before ruling that any line, object, or action is absent from a
scene, you must be able to point at your evidence: either a NOT FOUND search result for
its quoted text, or the FULL text of that scene shown above without a TRUNCATED marker.
A truncated scene plus no search result means you cannot rule absence at all — say the
evidence is insufficient instead of inventing an absence.

The FULL-SCRIPT SEARCH below is authoritative the other way: each quoted string from the
claim was mechanically searched across the ENTIRE screenplay. A hit proves that text IS on
the page in the named scene, even when that scene is not shown above — never rule a quoted
line absent when the search found it. "NOT FOUND anywhere" is the only license to say a
quoted string is not in the script. Before rejecting a fact as an unstated assumption,
check the search results AND the shown scenes: a fact stated anywhere the search surfaced
is a stated fact. The inference rule cuts both ways: attributes the script assigns to one
thing must not be silently transferred to another (a syndicate described as Asian does not
make its individually-described boss Asian).

SOURCE AUTHORITY: weigh whether each excerpt's SOURCE speaks with authority for the
premise's domain — a claim about a national ratings body needs that body or reporting on
it, not an unrelated council's meeting minutes; a legal doctrine needs more than a single
obscure aggregator. Real support from a non-authoritative source is PARTIAL, not
SUPPORTED.

CLAIM (severity {severity}, category {category}):
{finding}

REMEDY ASSERTED: {remedy}

SCRIPT CONTEXT (authoritative, scenes {scene_ids}):
{script_context}

FULL-SCRIPT SEARCH (mechanical, whole screenplay):
{search_results}

CITED EXCERPTS:
{citations}
"""

# 28k chars ≈ a dozen full script pages. Run 6 proved the window problem
# recurses at every aperture: run 4 was cross-scene (fixed), run 6 was WITHIN
# long scenes — the verifier saw the rooftop toast at the top of S012 and
# denied the nudity 100 lines down. Input is cheap (76% implicit cache hits);
# false rejections are not.
_MAX_CONTEXT_CHARS = 28000
_PER_SCENE_FLOOR = 2400


def _scene_context(flag: dict[str, Any], state: Any) -> str:
    """The flag's anchor scenes, fairly truncated. A truncation is MARKED — a verifier
    concluding "not in the script" from text this function silently cut would reject
    true findings (it happened; see the F204/F301 postmortem in the git history)."""
    text = state.get("script_text", "")
    by_id = {s["scene_id"]: s for s in state.get("scenes", [])}
    # The claim's evidence sometimes lives outside its anchor scenes (a desk
    # anchored a Sbarro finding at S019 while quoting S023; the verifier,
    # shown only S019, fabricated "Sbarro is not mentioned in S023" and killed
    # a true finding). Include every scene the FINDING ITSELF references.
    remedy = flag.get("remedy") or {}
    referenced = _re.findall(
        r"\bS\d{3}\b",
        " ".join([str(flag.get("finding") or ""), str(remedy.get("detail") or "")]),
    )
    sids = list(dict.fromkeys([*flag["scene_ids"], *referenced]))
    scenes = [by_id[sid] for sid in sids if sid in by_id]
    if not scenes:
        return "(scene text unavailable)"
    # Floor: a wide flag must still give the verifier enough of each scene to
    # judge — 480-char slivers made it (correctly) refuse to rule, which turned
    # the widest flags into the least-verified ones.
    per_scene = max(_PER_SCENE_FLOOR, _MAX_CONTEXT_CHARS // len(scenes))
    chunks: list[str] = []
    for scene in scenes:
        start, end = scene["raw_span"]
        chunk = text[start:end].strip()
        if len(chunk) > per_scene:
            cut = len(chunk) - per_scene
            chunk = chunk[:per_scene] + (
                f"\n[... SCENE TRUNCATED — {cut} more characters follow that you were NOT "
                "shown; you cannot rule anything absent from this scene ...]"
            )
        chunks.append(f"=== {scene['scene_id']} ===\n{chunk}")
    return "\n\n".join(chunks)


_MAX_SEARCH_TERMS = 8
_QUOTED_RE = _re.compile(r'["“]([^"“”]{4,120})["”]')
# single-quoted spans need an inner space and clean boundaries so apostrophes
# ("Vick's") don't pair up — findings quote dialogue in single quotes too, and
# run 6's Sbarro rejection sailed past a double-quote-only extractor (3rd time)
_SINGLE_QUOTED_RE = _re.compile(
    "(?:^|[\\s(\\[\u2014\u2013-])[\u2018']([^\u2018\u2019']{6,120})[\u2019'](?=$|[\\s).,;:!?\\]])"
)


def _quoted_spans(text: str) -> list[str]:
    spans = list(_QUOTED_RE.findall(text))
    spans += [m for m in _SINGLE_QUOTED_RE.findall(text) if " " in m]
    return list(dict.fromkeys(s.strip() for s in spans if s.strip()))


# 1:1 character translations ONLY — positions into the original text stay
# valid. The real script uses curly apostrophes (It\u2019s), curly quotes, and
# em-dashes; findings and rejections quote in straight ASCII. Without this,
# any quoted line containing an apostrophe fails both the exact and the
# whitespace-flexible match and the search reports a false absence.
_CANON = str.maketrans(
    {
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2014": "-",
        "\u2013": "-",
        "\u2026": ".",
    }
)


def _canon(s: str) -> str:
    return s.translate(_CANON).lower()


def _find_in_script(span: str, text: str) -> int:
    """Position of span in the script: exact, then whitespace-flexible, both on
    canonicalized text (curly/straight quote and dash variants unified); -1 if
    absent. Word-splitting also tolerates a hyphen/linebreak between words."""
    cspan, ctext = _canon(span), _canon(text)
    pos = ctext.find(cspan)
    if pos >= 0:
        return pos
    words = [w for w in _re.split(r"[\s-]+", cspan) if w]
    if not words:
        return -1
    m = _re.search(r"[\s-]+".join(_re.escape(w) for w in words), ctext)
    return m.start() if m else -1


# High-precision absence phrasing only: an overturn must be near-certain. A
# bare "no "/"never"/"without" near a quote used as SUPPORTING evidence
# ("script shows 'X' but no permit exists") must not trigger.
_ABSENCE_RE = _re.compile(
    r"(?:does not|do not|doesn't|don't|did not|didn't)"
    r" (?:appear|occur|exist|contain|feature|show|include)"
    r"|not (?:present|depicted|shown|mentioned|spoken|found|appear)"
    r"|appears? nowhere|nowhere in|absent from|contains? no\b|no such"
    r"|not in (?:the )?(?:script|screenplay|scene|dialogue|s\d{3})"
    r"|no (?:depicted|on-screen|onscreen)"
)


def demotion_entries(dropped: list[dict[str, Any]]) -> dict[str, list[str]]:
    """{open_questions state key: entries} for sourcing-failure rejections.

    A claim the verifier could not SOURCE is not a claim it disproved, so it
    stays on the record as an honest unknown and its scenes never flip to "No
    known issue". Shared so the salvage path behaves like the main one — that
    divergence is how a fair CSATF-titles rejection took a 110mph missing-door
    drive dark on runs that aborted.
    """
    out: dict[str, list[str]] = {}
    for r in dropped:
        if r.get("failure_mode") not in ("premise_unsupported", "citation_offtopic"):
            continue
        key = f"open_questions:{r.get('agent', 'clearance_counsel')}"
        # Identify the unresolved item by its metadata — do NOT restate the
        # desk's prose. That text was truncated mid-sentence ("...consume
        # Jägermeister shots in") and carried the very specifics the citation
        # failed to support (an alcohol-and-driving framing the script
        # contradicts), turning a demotion into a back-door restatement of a
        # claim verification had just declined to stand behind.
        subject = str(r.get("category") or "finding").replace("_", " ")
        scenes = ", ".join(r.get("scene_ids") or []) or "unspecified scenes"
        out.setdefault(key, []).append(
            f"Unresolved — the {subject} finding ({r['flag_id']}, {scenes}) was filed but its "
            "citation support did not hold. The claim was not disproven; it needs an "
            "authoritative source before it can be relied on."
        )
    return out


# A rejection resting on BOTH a false unstated-fact ground AND a real sourcing
# ground (run 12, F3009: the ages ARE stated in S004, but the labor-statute
# excerpts genuinely don't hold) must not be blind-flipped to SUPPORTED — strike
# only the false ground and let the sourcing ground route it honestly.
_SOURCING_GROUND_RE = _re.compile(
    r"excerpts? (?:do(?:es)? not|fail|lack)|citations? (?:do(?:es)? not|fail)"
    r"|not (?:establish|support)|no authoritative source",
    _re.IGNORECASE,
)


def _apply_overturns(
    flags: list[dict[str, Any]], verdicts: dict[str, dict[str, Any]], state: Any
) -> list[tuple[str, str, str]]:
    """Assertion 1 over a verdict set: overturn every UNSUPPORTED verdict whose
    reason asserts an absence — or calls a fact unstated — that the script text
    disproves. Mutates `verdicts`; returns [(flag_id, note, scene_id)] for
    reporting. Runs on the main pass, the re-source pass, and the salvage path —
    a false rejection must not survive ANY route to the record."""
    overturned: list[tuple[str, str, str]] = []
    for f in flags:
        v = verdicts.get(f["flag_id"])
        if not v or v.get("verdict") != "UNSUPPORTED":
            continue
        reason = str(v.get("reason") or "")
        hit = _overturned_by_script(reason, state)
        claim = "absent"
        if hit is None:
            hit = _stated_fact_overturn(reason, state, str(f.get("finding") or ""))
            claim = "unstated"
        if hit is None:
            continue
        span, sid = hit
        # Widen coordinates to the scene that carries the fact — the finding argued
        # from a window that did not contain it (F3009: ages in S004, not S084).
        if claim == "unstated" and sid not in (f.get("scene_ids") or []):
            f["scene_ids"] = sorted({*(f.get("scene_ids") or []), sid}, key=lambda x: int(x[1:]))
        if claim == "unstated" and _SOURCING_GROUND_RE.search(reason):
            verdicts[f["flag_id"]] = {
                "verdict": "UNSUPPORTED",
                "reason": (
                    "GROUND PARTIALLY OVERTURNED: the 'unstated fact' objection was false — "
                    f"the script states the specifics ({span[:60]}) in {sid}. The sourcing "
                    "objection stands. Original rejection: " + reason[:200]
                ),
                "failure_mode": "premise_unsupported",
                "ground_overturned": True,
            }
            overturned.append(
                (f["flag_id"], f"false 'unstated fact' ground struck ({span[:50]})", sid)
            )
            continue
        detail = (
            f'the rejection asserted "{span[:60]}" is absent'
            if claim == "absent"
            else f"the rejection called the specifics ({span[:60]}) unstated"
        )
        verdicts[f["flag_id"]] = {
            "verdict": "SUPPORTED",
            "reason": (
                f"OVERTURNED by assertion: {detail}, but the script states it in {sid}. "
                "Original rejection: " + reason[:200]
            ),
            "failure_mode": "none",
            "overridden": True,
        }
        overturned.append((f["flag_id"], f"rejection OVERTURNED — {detail}", sid))
    return overturned


def _overturned_by_script(reason: str, state: Any) -> tuple[str, str] | None:
    """ASSERTION 1 (run-6 harness): no rejection may assert that a string is
    absent when a full-text search of the script finds it. Returns (span,
    scene_id) when the rejection quotes text that EXISTS in the script and the
    surrounding sentence asserts its absence — the deterministic catch for
    'The line X does not appear in the screenplay' about a line that does."""
    text = str(state.get("script_text") or "")
    if not text or not reason:
        return None
    low_reason = reason.lower()
    for span in _quoted_spans(reason):
        pos = _find_in_script(span, text)
        if pos < 0:
            continue  # quote genuinely absent — the rejection may stand
        qpos = low_reason.find(span.lower()[:40])
        window = low_reason[max(0, qpos - 90) : qpos + len(span) + 90] if qpos >= 0 else low_reason
        if _ABSENCE_RE.search(window):
            sid = next(
                (
                    s["scene_id"]
                    for s in state.get("scenes", [])
                    if s["raw_span"][0] <= pos < s["raw_span"][1]
                ),
                "the script",
            )
            return span, sid
    return None


# The sibling of the absence overturn, for the OTHER false-rejection shape: the
# verifier calls a fact "unstated/assumed" because it read a partial window, when
# the script states it elsewhere (F3011: the daughters' ages, in S004, not the
# finding's own coordinates — which took the whole minor-safety finding down).
_UNSTATED_RE = _re.compile(
    r"unstated|assum\w+"
    r"|does not (?:specify|state|mention|establish|say)"
    r"|not (?:specified|stated|established)|no mention of",
    _re.IGNORECASE,
)
_NUM_WORDS = {
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
    "10": "ten",
    "11": "eleven",
    "12": "twelve",
}
# Common capitalized words a sentence throws off that are not the distinctive proper
# nouns whose co-occurrence anchors the overturn.
_COMMON_CAPS = frozenset(
    {
        "the",
        "this",
        "that",
        "these",
        "those",
        "scene",
        "script",
        "screenplay",
        "before",
        "after",
        "under",
        "when",
        "while",
        "both",
        "their",
        "finding",
        "flag",
        "note",
        "text",
        "claim",
        "cara",
        "mpa",
        "bbfc",
        "int",
        "ext",
        "and",
        "but",
        "for",
        "prohibition",
        "does",
        "did",
        "how",
        "what",
        "where",
        "why",
        "who",
        "was",
        "were",
        "has",
        "have",
        "its",
        "it",
        "he",
        "she",
        "they",
        "them",
        "his",
        "her",
        "if",
        "no",
        "not",
    }
)
_NAME_NUM_NEAR = 40  # a claimed age/count must sit beside the name, not just in the scene
_MIN_ANCHOR_NAMES = 2  # need >=2 distinctive names co-occurring for near-certainty
_MAX_ANCHOR_SCENES = 3  # if the names appear together in more scenes, the anchor is ambiguous


def _num_near_name(seg: str, propers: set[str], n: str) -> bool:
    """Is number n (digit OR word form) within _NAME_NUM_NEAR chars of a named
    person in this scene? 'Haylee is two' confirms; a stray 7 elsewhere does not."""
    forms = [n] + ([_NUM_WORDS[n]] if n in _NUM_WORDS else [])
    for p in propers:
        for pm in _re.finditer(_re.escape(p.lower()), seg):
            window = seg[max(0, pm.start() - _NAME_NUM_NEAR) : pm.end() + _NAME_NUM_NEAR]
            if any(
                _re.search(rf"(?<![A-Za-z0-9]){_re.escape(f)}(?![A-Za-z0-9])", window)
                for f in forms
            ):
                return True
    return False


def _propers_near_numbers(body: str, nums: set[str]) -> set[str]:
    """Distinctive capitalized names within _NAME_NUM_NEAR chars of a claimed
    number in `body` — the names the claim actually ties its numbers to
    ('Haylee, age 2' -> Haylee), excluding sentence-case noise."""
    out: set[str] = set()
    for n in nums:
        forms = [n] + ([_NUM_WORDS[n]] if n in _NUM_WORDS else [])
        for form in forms:
            for m in _re.finditer(rf"(?<![A-Za-z0-9]){_re.escape(form)}(?![A-Za-z0-9])", body):
                window = body[max(0, m.start() - _NAME_NUM_NEAR) : m.end() + _NAME_NUM_NEAR]
                out |= {
                    w
                    for w in _re.findall(r"\b[A-Z][a-z]{2,}\b", window)
                    if w.lower() not in _COMMON_CAPS
                }
    return out


def _stated_fact_overturn(reason: str, state: Any, finding: str = "") -> tuple[str, str] | None:
    """Unstated-fact rejections: if the distinctive proper nouns the claim ties its
    numbers to (>= 2) all co-occur in ONE scene, and every claimed number sits beside
    a name there (digit or word), the fact IS stated — the verifier reasoned from a
    partial window. Names are anchored to the numbers first (in the reason, then the
    FINDING — run 12's rejection said only 'the daughters'; the finding names them);
    whole-reason extraction is the fallback. Returns (names, scene_id). High
    precision: ambiguous when the names appear together in more than three scenes."""
    text = str(state.get("script_text") or "")
    scenes = state.get("scenes", [])
    if not text or not scenes or not _UNSTATED_RE.search(reason):
        return None
    # Numbers come only from the sentence(s) carrying the unstated-fact ground —
    # a mixed rejection's sourcing sentence contributes statute numbers (NRS 609,
    # 3-hour limits) that would poison the scene match.
    sentences = _re.split(r"(?<=[.;])\s+", reason)
    claim_text = " ".join(s for s in sentences if _UNSTATED_RE.search(s)) or reason
    nums = set(_re.findall(r"(?<![A-Za-z0-9])\d{1,3}(?![0-9])", claim_text))
    propers = _propers_near_numbers(claim_text, nums)
    if len(propers) < _MIN_ANCHOR_NAMES and finding:
        propers |= _propers_near_numbers(finding, nums)
    if len(propers) < _MIN_ANCHOR_NAMES:
        propers = {
            w for w in _re.findall(r"\b[A-Z][a-z]{2,}\b", reason) if w.lower() not in _COMMON_CAPS
        }
    if len(propers) < _MIN_ANCHOR_NAMES:
        return None
    matches: list[str] = []
    for s in scenes:
        seg = text[s["raw_span"][0] : s["raw_span"][1]].lower()
        if not all(p.lower() in seg for p in propers):
            continue
        if nums and not all(_num_near_name(seg, propers, n) for n in nums):
            continue
        matches.append(s["scene_id"])
    if not matches or len(matches) > _MAX_ANCHOR_SCENES:
        return None
    return ", ".join(sorted(propers)), matches[0]


# ---- coordinate completion (run-13 item 4): runs BEFORE verification ---------
# A finding's evidence must sit inside its declared window before the verifier
# judges it — run 10 rejected a true finding whose evidence lived outside the
# window; run 11 silently passed a number asserted under the wrong scene. Only
# SCRIPT-FACT figures anchor (ages, on-page counts): a number beside $, %, §,
# or a statute/bulletin token is a PREMISE figure that resolves in excerpts,
# never in scenes — as drafted without this split, the pass would have chased
# F3009's legitimate NRS/CCR numbers.
_PREMISE_NUM_CONTEXT = _re.compile(
    r"[$§%]\s*[\d,]|[\d.]\s*%|\b(?:CFR|NRS|CCR|USC|Reg(?:\.|istration)?|Bulletin|No\.)"
    r"\s*#?\s*\d|\d\s*(?:CFR|USC)|\bx\s?\d|\d\s?x\b",
    _re.IGNORECASE,
)
_COORD_WIDEN_CAP = 2  # umbrella philosophy: widen a little, never re-anchor a sprawl


def _scriptfact_nums(text: str) -> set[str]:
    """1-3 digit numbers that could be facts ON THE PAGE (ages, counts, speeds)
    — excludes numbers in premise context (money, percents, statutes, census
    'x8' tallies) and scene ids (letter-adjacent digits never match)."""
    out: set[str] = set()
    for m in _re.finditer(r"(?<![A-Za-z0-9])(\d{1,3})(?![0-9])", text):
        ctx = text[max(0, m.start() - 14) : m.end() + 14]
        if _PREMISE_NUM_CONTEXT.search(ctx):
            continue
        out.add(m.group(1))
    return out


def _complete_coordinates(flag: dict[str, Any], state: Any) -> list[tuple[str, str, str]]:
    """Resolve each number-anchored proper-noun claim in the FINDING body to a
    scene; widen the flag's coordinates (cap +2) when a claim resolves outside
    them. Per-claim: a number is tied to the names within _NAME_NUM_NEAR of it
    in the body, and resolves only to a scene where those names appear with the
    number beside one of them — the same proximity guards as the overturn.
    Returns [(scene_id, number, names)] for the manifest."""
    text = str(state.get("script_text") or "")
    scenes = state.get("scenes", [])
    body = str(flag.get("finding") or "")
    if not text or not scenes or not body:
        return []
    declared = set(flag.get("scene_ids") or [])
    added: list[tuple[str, str, str]] = []
    for n in sorted(_scriptfact_nums(body)):
        propers = _propers_near_numbers(body, {n})
        if not propers:
            continue
        matches = []
        for s in scenes:
            seg = text[s["raw_span"][0] : s["raw_span"][1]].lower()
            if all(p.lower() in seg for p in propers) and _num_near_name(seg, propers, n):
                matches.append(s["scene_id"])
        if not matches or len(matches) > _MAX_ANCHOR_SCENES:
            continue  # unresolved or ambiguous: the verifier judges as filed
        for sid in matches:
            if sid not in declared and len(added) < _COORD_WIDEN_CAP:
                added.append((sid, n, ", ".join(sorted(propers))))
                declared.add(sid)
    if added:
        flag["scene_ids"] = sorted(declared, key=lambda x: int(x[1:]))
    return added


_MIN_SCRUBBED_BEAT = 15  # a remainder shorter than this is no longer an action


def _scrub_cutlist(beats: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Strip rule-shaped clauses from cut-list beats, keeping the action.
    Returns (scrubbed_beats, misses) where each miss is (original_beat,
    matched_phrase) for a beat that could not be cleanly stripped — those ship
    unmodified. Never deletes a beat."""
    from greenlight.tools.toolbelt import _NORMATIVE_RULE_RE

    out: list[str] = []
    misses: list[tuple[str, str]] = []
    for beat in beats:
        m = _NORMATIVE_RULE_RE.search(beat or "")
        if not m:
            out.append(beat)
            continue
        # excise the clause containing the match: back to the nearest clause
        # delimiter, forward to the sentence end
        start = max(beat.rfind(",", 0, m.start()), beat.rfind(";", 0, m.start()))
        start = start if start >= 0 else m.start()
        end_m = _re.search(r"[.;]", beat[m.end() :])
        end = m.end() + end_m.start() if end_m else len(beat)
        remainder = (beat[:start].rstrip(" ,;") + beat[end:]).strip(" ,;")
        if len(remainder) >= _MIN_SCRUBBED_BEAT and not _NORMATIVE_RULE_RE.search(remainder):
            out.append(remainder if remainder.endswith(".") else remainder + ".")
        else:
            out.append(beat)  # fail visible, never mangle
            misses.append((beat, m.group(0)))
    return out, misses


_FACT_PROP_CAP = 6  # survivors re-verified per run against established facts


def _misstatement_facts(dropped: list[dict[str, Any]]) -> list[tuple[set[str], str]]:
    """The script facts that script_misstatement rejections establish, with the
    scenes they speak about — [(scene_ids, rejection_reason)]. A verifier that
    caught S066 parked has established a fact about S066 for the WHOLE report,
    not just its own finding; every survivor sharing those scenes must face it
    (run 12: F4012 rejected for 'drinking while driving' being false while F2003
    shipped the same claim with a remedy)."""
    facts: list[tuple[set[str], str]] = []
    for r in dropped:
        if r.get("failure_mode") != "script_misstatement":
            continue
        reason = str(r.get("rejection_reason") or "")
        sids = set(_re.findall(r"\bS\d{3}\b", reason)) or set(r.get("scene_ids") or [])
        if reason and sids:
            facts.append((sids, reason))
    return facts


_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "her",
        "his",
        "how",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "may",
        "more",
        "most",
        "must",
        "no",
        "not",
        "of",
        "on",
        "one",
        "only",
        "or",
        "other",
        "our",
        "out",
        "over",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "under",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "will",
        "with",
        "would",
        "you",
        "your",
    ]
)
_MIN_TERM_LEN = 4


def _absent_terms(claim_text: str, script_lower: str) -> str:
    """Every substantive word of the claim that appears NOWHERE in the script,
    comma-joined. The famous-film contamination probe: a Hangover draft finding
    asserted 'live animals (rooster and tiger)... a baby left unattended' — the
    tiger and the baby are from the released 2009 film, not this draft. The
    verifier reads the list; legal vocabulary in it is noise, an on-page noun
    in it is a misstatement. Stem matching (first {_MIN_TERM_LEN} chars) keeps
    morphology out of it: run 6 rejected a real finding because 'bloody' isn't
    on a page where 'blood' is \u2014 match the event, not the desk's adjectives.
    High precision over recall: a word sharing a stem with ANY script text is
    treated as present."""
    words = {w.strip(".,;:()[]'\"!?" + "\u2014\u2013-").lower() for w in claim_text.split()}
    words = {w for w in words if w.isalpha() and len(w) >= _MIN_TERM_LEN and w not in _STOPWORDS}
    missing = sorted(
        w for w in words if w not in script_lower and w[:_MIN_TERM_LEN] not in script_lower
    )
    return ", ".join(missing[:40])


def _search_context(flag: dict[str, Any], state: Any) -> str:
    """Mechanical whole-script search for every quoted string in the claim.
    The verifier's window bug (run 4: four of five rejections false) was
    absence rulings made from a partial window — 'Sbarro is not in dialogue'
    while both lines sat in a scene the finding never named. The search is
    deterministic; the verifier just has to read it."""
    text = str(state.get("script_text") or "")
    if not text:
        return "(script text unavailable — make no absence rulings)"
    remedy = flag.get("remedy") or {}
    source = " ".join([str(flag.get("finding") or ""), str(remedy.get("detail") or "")])
    terms = _quoted_spans(source)  # double AND single quotes, curly or straight
    by_span = [(s["raw_span"][0], s["raw_span"][1], s["scene_id"]) for s in state.get("scenes", [])]
    lines: list[str] = []
    if absent := _absent_terms(source, _canon(text)):
        lines.append(
            "CLAIM WORDS (word-stems) FOUND NOWHERE IN THE SCREENPLAY — advisory only; "
            "legal/industry vocabulary, adjectives, and paraphrase land here and prove "
            f"NOTHING: {absent}"
        )
    for term in terms[:_MAX_SEARCH_TERMS]:
        pos = _find_in_script(term, text)
        if pos < 0:
            lines.append(f'- "{term}" — NOT FOUND anywhere in the screenplay')
            continue
        sid = next((s for a, b, s in by_span if a <= pos < b), "outside any scene")
        snippet = " ".join(text[max(0, pos - 100) : pos + len(term) + 100].split())
        lines.append(f'- "{term}" — FOUND in {sid}: “…{snippet}…”')
    if not lines:
        return "(no quoted strings in the claim to search for)"
    return "\n".join(lines)


def _blinded_prompt(flag: dict[str, Any], script_context: str, search_results: str) -> str:
    citations = "\n\n".join(
        f'[{i + 1}] {c.get("title") or c.get("url") or "untitled"}\n"{c["excerpt"]}"'
        for i, c in enumerate(flag["citations"])
    )
    remedy = f"{flag['remedy']['action']} — {flag['remedy']['detail']}"
    return VERIFIER_PROMPT.format(
        severity=flag["severity"],
        category=flag["category"],
        finding=flag["finding"],
        remedy=remedy,
        scene_ids=", ".join(flag["scene_ids"]),
        script_context=script_context,
        search_results=search_results,
        citations=citations,
    )


def apply_verdicts(
    flags: list[dict[str, Any]], verdicts: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pure function: (surviving flags, rejected flags). PARTIAL caps severity at
    MEDIUM and marks the finding; UNSUPPORTED drops the flag. Missing verdicts keep
    the flag untouched — a broken verifier must not silently delete findings."""
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for flag in flags:
        v = verdicts.get(flag["flag_id"])
        if v is None or v["verdict"] == "SUPPORTED":
            if v is not None and v.get("fail_open"):
                # the verifier never ran — the flag survives, but it must not
                # impersonate a verified finding on any surface
                kept.append({**flag, "verification_unavailable": True})
            else:
                kept.append(flag)
            continue
        if v["verdict"] == "PARTIAL":
            marked = dict(flag)
            # Severity is a RISK judgment and stays untouched: the old MEDIUM
            # cap parked close-proximity blank fire below a location fee in
            # the sort order because its citation carried a caveat. PARTIAL is
            # a visible verification marker, not a risk downgrade.
            marked["finding"] = "[partially supported] " + marked["finding"]
            kept.append(marked)
        else:
            # script_misstatement is recoverable too — via correct-and-refile,
            # not re-sourcing. Excluding it here made the correction branch
            # dead code, so every misstatement rejection (even one resting on
            # a factual error in a single clause) deleted the whole finding.
            recoverable = v.get("failure_mode") in (
                "premise_unsupported",
                "citation_offtopic",
                "script_misstatement",
            )
            rejected.append(
                {
                    **flag,
                    "rejection_reason": v["reason"],
                    "failure_mode": v.get("failure_mode", "none"),
                    "recoverable": recoverable and not flag.get("resourced"),
                }
            )
    return kept, rejected


async def _verify_flag(
    client: Any,
    flag: dict[str, Any],
    script_context: str,
    search_results: str,
    sem: asyncio.Semaphore,
) -> dict:
    async with sem:
        delay = 10.0
        for attempt in range(_MAX_ATTEMPTS):
            try:
                res = await client.aio.models.generate_content(
                    model=MODEL,
                    contents=_blinded_prompt(flag, script_context, search_results),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=Verdict,
                        temperature=0.0,
                    ),
                )
                v = Verdict.model_validate_json(res.text)
                # mirror _verify_one: without failure_mode a salvage-path
                # rejection is permanently mislabeled "none" on the record
                return {"verdict": v.verdict, "reason": v.reason, "failure_mode": v.failure_mode}
            except Exception:
                if attempt == _MAX_ATTEMPTS - 1:
                    # Fail open with a marker: never silently drop a flag
                    # because the VERIFIER errored.
                    return {
                        "verdict": "SUPPORTED",
                        "reason": "verifier unavailable",
                        "fail_open": True,
                    }
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)


async def verify_standalone(
    flags: list[dict[str, Any]], state: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """The same blinded fan-out, runnable outside the agent tree. The salvage
    path uses this when a run aborts after desks filed but before verification —
    a partial report must still be a VERIFIED partial report."""
    from google import genai

    client = genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        http_options=_RETRY_HTTP,
    )
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _one(f: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        return f["flag_id"], await _verify_flag(
            client, f, _scene_context(f, state), _search_context(f, state), sem
        )

    results = await asyncio.gather(*[_one(f) for f in flags])
    verdicts = dict(results)
    _apply_overturns(flags, verdicts, state)  # assertion 1 holds on the salvage path too
    return verdicts


_RESOURCE_CAP = 6  # re-source the worst-hit few, not the world
_RESOURCE_CITES = 3  # replacement citations per re-sourced flag


def _fresh_citations(
    flag: dict[str, Any], state: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """One live search aimed at the claim's premise; top verbatim excerpts
    become replacement citations. Module-level so tests can monkeypatch.

    The result passes the SAME tier gate a filed flag faces: a re-sourced
    BLOCKER/HIGH/MEDIUM flag once shipped on background hosts because this
    path bypassed file_flag entirely. Background-host excerpts are dropped
    here for MEDIUM+ severities; the search is grouped under the run's
    Parallel session and counted in run telemetry."""
    from greenlight.tools import toolbelt

    state = state or {}
    cat = str(flag.get("category") or "")
    lead = str(flag.get("finding", ""))[:120]
    # Category-matched retrieval: six of seven rejections in one run shared
    # "right claim, wrong authority class" — a generic query re-found the
    # same wrong class. Aim the re-source at the authority the claim needs.
    if cat.startswith(("location_release", "trade_libel_venue")):
        query_seed = f"filming location agreement rates production {lead}"
    elif cat.startswith("rating_"):
        query_seed = f"CARA MPA rating rationale {cat.removeprefix('rating_')} filmratings {lead}"
    elif cat.startswith(("stunt_", "firearms", "minor_safety", "animal_safety", "weather")):
        query_seed = f"CSATF safety bulletin requirements {cat.replace('_', ' ')} {lead}"
    elif cat.startswith("territory_"):
        query_seed = f"{cat.replace('_', ' ')} media regulation film censorship {lead}"
    elif cat.startswith(("sync_", "master_", "music")):
        query_seed = f"sync master use license practice {lead}"
    else:
        query_seed = f"{cat.replace('_', ' ')} {lead}"
    try:
        res = toolbelt._live_search(
            objective=f"Authoritative support for: {str(flag.get('finding', ''))[:200]}",
            queries=[query_seed],
            session_id=str(state.get("parallel_session_id") or "") or None,
        )
        state["resource_searches"] = int(state.get("resource_searches") or 0) + 1
    except Exception:
        return []
    strict = flag.get("severity") in ("BLOCKER", "HIGH", "MEDIUM")
    cits: list[dict[str, Any]] = []
    for r in res.get("results", []) or []:
        if strict and toolbelt._is_background_host(r.get("url") or ""):
            continue  # the tier gate, applied where file_flag would have applied it
        for ex in (r.get("excerpts") or [])[:1]:
            cits.append(
                {
                    "source_type": "web",
                    "title": r.get("title", ""),
                    "url": r.get("url"),
                    "excerpt": ex,
                    "retrieved_at": None,
                    "via": "parallel_search_resource",
                }
            )
        if len(cits) >= _RESOURCE_CITES:
            break
    return cits


class VerificationPanel(BaseAgent):
    """Runtime fan-out: one Gemini verifier per flag, concurrently, blinded."""

    async def _correct_finding_and_remedy(
        self, client: Any, flag: dict[str, Any], script_context: str, sem: asyncio.Semaphore
    ) -> tuple[str, str] | None:
        """Fact-propagation correction: rewrite BOTH the finding and the remedy to
        state only what the established facts and scene text support. Correcting
        the body while the remedy still directs cutting a beat that is not in the
        script is the landed-structurally failure again. Returns (finding,
        remedy_detail) or None when the core claim does not survive."""
        remedy = (flag.get("remedy") or {}).get("detail") or ""
        prompt = (
            "A clearance finding contradicts script facts that independent verification "
            "has established. Rewrite the FINDING and its REMEDY to state only what the "
            "scene text and established facts below support, preserving the underlying "
            "exposure claim if it survives. If the core claim does not survive, reply "
            "with exactly: UNSALVAGEABLE.\n\n"
            f"FINDING:\n{flag.get('finding', '')}\n\n"
            f"REMEDY:\n{remedy}\n\n"
            f"WHY IT FAILED:\n{flag.get('rejection_reason', '')}\n\n"
            f"SCENE TEXT AND ESTABLISHED FACTS:\n{script_context}\n\n"
            'Reply as JSON: {"finding": "...", "remedy": "..."} (or UNSALVAGEABLE).'
        )
        async with sem:
            try:
                res = await client.aio.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=_CorrectedFlag,
                        temperature=0.0,
                    ),
                )
                out = _CorrectedFlag.model_validate_json(res.text)
            except Exception:
                return None
        if not out.finding.strip() or "UNSALVAGEABLE" in out.finding[:40].upper():
            return None
        return out.finding.strip()[:1500], out.remedy.strip()[:1500]

    async def _correct_finding(
        self, client: Any, flag: dict[str, Any], script_context: str, sem: asyncio.Semaphore
    ) -> str | None:
        """Rewrite a misstated finding to state only what the scene text
        supports, preserving the exposure claim. Returns None when the core
        claim does not survive the correction (then the rejection stands)."""
        prompt = (
            "A clearance finding was rejected because it misstates the screenplay. "
            "Rewrite it to state ONLY what the scene text below supports, preserving "
            "the underlying exposure claim if it survives the correction. If the core "
            "claim does not survive, reply with exactly: UNSALVAGEABLE.\n\n"
            f"REJECTED FINDING:\n{flag.get('finding', '')}\n\n"
            f"REJECTION REASON:\n{flag.get('rejection_reason', '')}\n\n"
            f"SCENE TEXT:\n{script_context}\n\n"
            "Reply with the corrected finding text alone (or UNSALVAGEABLE)."
        )
        async with sem:
            try:
                res = await client.aio.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.0),
                )
            except Exception:
                return None
        fixed = (res.text or "").strip()
        if not fixed or "UNSALVAGEABLE" in fixed[:40].upper():
            return None
        return fixed[:1500]

    async def _reconcile_rating(
        self,
        client: Any,
        pred: dict[str, Any],
        kept: list[dict[str, Any]],
        dropped: list[dict[str, Any]],
        sem: asyncio.Semaphore,
    ) -> dict[str, Any] | None:
        """The ratings desk files its rationale and cut list DURING its loop —
        before verification exists. A rejected finding must take its clause of
        the rationale and its cut with it, or the report contradicts itself
        (run 4: a cut for open-bottle drinking-while-driving derived from a
        finding the verifier rejected because the car is parked). Returns the
        revised {rationale, beats_to_cut} or None to leave the prediction as
        filed (fail-open: reconciliation must never delete the prediction)."""
        rejected_lines = "\n".join(
            f"- {r['flag_id']}: {str(r.get('finding', ''))[:300]}\n"
            f"  REJECTED BECAUSE: {str(r.get('rejection_reason', ''))[:300]}"
            for r in dropped
        )
        surviving = "\n".join(
            f"- {f['flag_id']} ({f['severity']} {f['category']}): {str(f.get('finding', ''))[:160]}"
            + (
                f" | REMEDY: {str((f.get('remedy') or {}).get('detail') or '')[:160]}"
                if str(f.get("category", "")).startswith("rating_")
                else ""
            )
            for f in kept
        )
        prompt = (
            "A screenplay's MPA rating prediction was filed before citation verification. "
            "Verification has now REJECTED some findings; the script facts stated in the "
            "rejection reasons are authoritative. Revise the rating rationale and the cut "
            "list so neither rests on rejected material: remove or amend ONLY clauses and "
            "cuts whose sole support was a rejected finding, keep everything else verbatim, "
            "and never invent new content. ONE exception permits adding: when a SURVIVING "
            "finding's remedy names a specific rating-driving cut (e.g. 'eliminate 2 of the "
            "3 F-words') that the cut list lacks, add that cut using the remedy's own words "
            "— the strongest single rating driver must never be missing from the levers.\n\n"
            f"CURRENT RATIONALE:\n{pred.get('rationale', '')}\n\n"
            "CURRENT CUT LIST:\n"
            + "\n".join(f"- {b}" for b in pred.get("beats_to_cut") or [])
            + f"\n\nREJECTED FINDINGS:\n{rejected_lines}\n\n"
            f"SURVIVING FINDINGS:\n{surviving}\n"
        )
        async with sem:
            try:
                res = await client.aio.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=_RatingReconcile,
                        temperature=0.0,
                    ),
                )
                out = _RatingReconcile.model_validate_json(res.text)
            except Exception:
                return None
        if not out.rationale.strip():
            return None
        return {"rationale": out.rationale.strip(), "beats_to_cut": out.beats_to_cut}

    async def _verify_one(
        self,
        client: Any,
        flag: dict[str, Any],
        script_context: str,
        search_results: str,
        sem: asyncio.Semaphore,
    ) -> dict:
        async with sem:
            delay = 10.0
            for attempt in range(_MAX_ATTEMPTS):
                try:
                    res = await client.aio.models.generate_content(
                        model=MODEL,
                        contents=_blinded_prompt(flag, script_context, search_results),
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=Verdict,
                            temperature=0.0,
                        ),
                    )
                    v = Verdict.model_validate_json(res.text)
                    return {
                        "verdict": v.verdict,
                        "reason": v.reason,
                        "failure_mode": v.failure_mode,
                    }
                except Exception:
                    if attempt == _MAX_ATTEMPTS - 1:
                        # Fail open with a marker: never silently drop a flag
                        # because the VERIFIER errored.
                        return {
                            "verdict": "SUPPORTED",
                            "reason": "verifier unavailable",
                            "fail_open": True,
                        }
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)

    async def _run_async_impl(  # noqa: PLR0912, PLR0915 - staged verify/re-source/reconcile sequence
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        from google import genai

        state = ctx.session.state
        from greenlight.tools.toolbelt import desk_flags

        flags = [f for d in DESKS for f in desk_flags(state, d)]
        # Run-13 guard manifest: every guard fire this panel makes, queryable
        # from the record — run 11 shipped an unaudited softener because "did
        # it fire anywhere else?" was unanswerable from the deliverable.
        manifest: list[dict[str, Any]] = []
        # COORDINATE COMPLETION (pre-verification): the window must contain the
        # evidence BEFORE the verifier judges against it.
        for f in flags:
            before = list(f.get("scene_ids") or [])
            for sid, num, names in _complete_coordinates(f, state):
                manifest.append(
                    {
                        "guard": "coordinate_completion",
                        "stage": "pre_verification",
                        "flag_id": f["flag_id"],
                        "matched": f"{names} + {num}",
                        "coords_before": before,
                        "coords_after": list(f["scene_ids"]),
                    }
                )
                yield Event(
                    invocation_id=ctx.invocation_id,
                    author=self.name,
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                text=f"⚖ {f['flag_id']} coordinates widened to {sid} — the "
                                f"body's claim ({names}, {num}) resolves there"
                            )
                        ],
                    ),
                )
        if not flags:
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                # downstream reads these keys (the Adjudicator templates
                # {rejected_summary}); an early return must still write them
                actions=EventActions(
                    state_delta={
                        "verified_flags": [],
                        "rejected_flags": [],
                        "rejected_summary": "(none)",
                    }
                ),
                content=types.Content(role="model", parts=[types.Part(text="No flags to verify.")]),
            )
            return

        client = genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            http_options=_RETRY_HTTP,
        )
        sem = asyncio.Semaphore(_CONCURRENCY)

        async def _one(f: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            return f, await self._verify_one(
                client, f, _scene_context(f, state), _search_context(f, state), sem
            )

        # Stream each verdict as it lands: the challenge-and-ruling is the part
        # of the run worth watching, so it must not arrive as one silent batch.
        verdicts: dict[str, dict[str, Any]] = {}
        for fut in asyncio.as_completed([_one(f) for f in flags]):
            f, v = await fut
            verdicts[f["flag_id"]] = v
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=f"⚖ {f['flag_id']}|{f['category']}|{f['severity']}|"
                            f"{v['verdict']}|{v['reason'][:160]}"
                        )
                    ],
                ),
            )
        # ASSERTION 1 (run-6 harness): no rejection may assert a string is
        # absent when the full-text search finds it. Deterministic, and it runs
        # BEFORE anything downstream (rejected_summary, demotions, reconcile)
        # can act on a false rejection.
        for fid, note, sid in _apply_overturns(flags, verdicts, state):
            v_after = verdicts.get(fid, {})
            manifest.append(
                {
                    "guard": "overturn",
                    "stage": "post_verification",
                    "flag_id": fid,
                    "matched": note,
                    "scene": sid,
                    "verdict_after": v_after.get("verdict"),
                    "overridden": bool(v_after.get("overridden")),
                    "ground_overturned": bool(v_after.get("ground_overturned")),
                }
            )
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=f"⚖ {fid} {note}; the script states it in {sid}")],
                ),
            )
        kept, dropped = apply_verdicts(flags, verdicts)

        # A5: a true finding killed by a bad citation goes around ONCE with
        # fresh sourcing — recall must not be capped by citation retrieval.
        recoverable = [r for r in dropped if r.get("recoverable")][:_RESOURCE_CAP]
        resourced_stats = {"attempted": len(recoverable), "recovered": 0}
        if recoverable:
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=f"↻ re-sourcing {len(recoverable)} rejection(s) whose failure "
                            "was the citations, not the claim: "
                            + ", ".join(r["flag_id"] for r in recoverable)
                        )
                    ],
                ),
            )
        for r in recoverable:
            if r.get("failure_mode") == "script_misstatement":
                # A factual slip (wrong character name) once deleted a whole
                # territory analysis. One correction round: restate the finding
                # to ONLY what the script supports, keep citations, re-verify.
                evidence = (
                    _scene_context(r, state)
                    + "\n\nFULL-SCRIPT SEARCH (authoritative):\n"
                    + _search_context(r, state)
                )
                fixed = await self._correct_finding(client, r, evidence, sem)
                if not fixed:
                    continue
                retry_flag = {**r, "finding": fixed, "resourced": True}
            else:
                new_cits = await asyncio.to_thread(_fresh_citations, r, state)
                if not new_cits:
                    continue
                retry_flag = {**r, "citations": new_cits, "resourced": True}
            retry_flag.pop("rejection_reason", None)
            retry_flag.pop("recoverable", None)
            v2 = await self._verify_one(
                client,
                retry_flag,
                _scene_context(retry_flag, state),
                _search_context(retry_flag, state),
                sem,
            )
            # assertion 1 screens the re-source verdict too
            _tmp = {retry_flag["flag_id"]: v2}
            _apply_overturns([retry_flag], _tmp, state)
            v2 = _tmp[retry_flag["flag_id"]]
            verdicts[r["flag_id"] + ":resourced"] = v2
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=f"↻ {r['flag_id']} re-sourced → "
                            f"{v2['verdict']}|{v2['reason'][:120]}"
                        )
                    ],
                ),
            )
            k2, _d2 = apply_verdicts([retry_flag], {r["flag_id"]: v2})
            if k2:
                # The BASE verdict still says UNSUPPORTED — pipeline rebuilds
                # record["verdicts"] from base ids only, so a recovered flag
                # shipped in record["flags"] while the verdict beside it called
                # it rejected. Promote the base verdict and clear the rejection
                # metadata the retry_flag inherited via {**r}.
                verdicts[r["flag_id"]] = v2
                for stale in ("failure_mode", "rejection_reason", "recoverable"):
                    for f in k2:
                        f.pop(stale, None)
                kept.extend(k2)
                dropped = [d for d in dropped if d["flag_id"] != r["flag_id"]]
                resourced_stats["recovered"] += 1

        # FACT PROPAGATION (run 12): verifiers are per-finding, so a script fact
        # one rejection establishes never reached the verifier of a SURVIVING
        # finding asserting the contradicted claim — the report shipped three
        # descriptions of one script moment: one rejected as wrong, one right,
        # one wrong with a remedy. Re-verify every survivor sharing scenes with
        # a script_misstatement rejection, with the established facts on the
        # record; a survivor the facts impeach gets one correct-and-refile round,
        # then drops. Deterministic collection and application; the model only
        # re-judges inside the already-blinded verifier.
        facts = _misstatement_facts(dropped)
        for f in [f for f in kept if any(set(f.get("scene_ids") or []) & fs for fs, _ in facts)][
            :_FACT_PROP_CAP
        ]:
            fid = f["flag_id"]
            blocks = [r for fs, r in facts if set(f.get("scene_ids") or []) & fs]
            fact_ctx = (
                "\n\nESTABLISHED SCRIPT FACTS — independent verification of THIS screenplay "
                "already confirmed these about the scenes below; they are authoritative over "
                "the claim's script facts:\n" + "\n".join(f"- {b}" for b in blocks)
            )
            v3 = await self._verify_one(
                client, f, _scene_context(f, state) + fact_ctx, _search_context(f, state), sem
            )
            if v3.get("fail_open") or not (
                v3["verdict"] == "UNSUPPORTED" and v3.get("failure_mode") == "script_misstatement"
            ):
                continue  # the facts do not impeach this survivor; first verdict stands
            verdicts[fid + ":pre_facts"] = verdicts.get(fid, {})
            evidence = (
                _scene_context(f, state)
                + fact_ctx
                + "\n\nFULL-SCRIPT SEARCH (authoritative):\n"
                + _search_context(f, state)
            )
            corrected = await self._correct_finding_and_remedy(
                client, {**f, "rejection_reason": v3["reason"]}, evidence, sem
            )
            recovered = False
            if corrected:
                new_finding, new_remedy = corrected
                # The refile re-enters the filing gate: a corrected rating finding
                # that launders the rule back in is not a recovery.
                from greenlight.tools.toolbelt import _normative_rule_problem

                if _normative_rule_problem(f.get("category", ""), new_finding, new_remedy):
                    corrected = None
            if corrected:
                new_finding, new_remedy = corrected
                retry_flag = {
                    **f,
                    "finding": new_finding,
                    "remedy": {**(f.get("remedy") or {}), "detail": new_remedy},
                    "fact_reconciled": True,
                }
                v4 = await self._verify_one(
                    client,
                    retry_flag,
                    _scene_context(retry_flag, state) + fact_ctx,
                    _search_context(retry_flag, state),
                    sem,
                )
                if v4["verdict"] != "UNSUPPORTED":
                    f["finding"] = new_finding
                    f["remedy"] = {**(f.get("remedy") or {}), "detail": new_remedy}
                    f["fact_reconciled"] = True
                    verdicts[fid] = v4
                    recovered = True
            if not recovered:
                kept = [k for k in kept if k["flag_id"] != fid]
                verdicts[fid] = v3
                dropped.append(
                    {
                        **f,
                        "rejection_reason": v3["reason"],
                        "failure_mode": "script_misstatement",
                    }
                )
            manifest.append(
                {
                    "guard": "fact_propagation",
                    "stage": "post_verification",
                    "flag_id": fid,
                    "outcome": "restated" if recovered else "dropped",
                    "matched": v3["reason"][:160],
                }
            )
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=(
                                f"⚖ {fid} restated against established script facts"
                                if recovered
                                else f"⚖ {fid} DROPPED by fact propagation — it asserts a claim "
                                "a verified rejection already disproved: " + v3["reason"][:120]
                            )
                        )
                    ],
                ),
            )

        # A sourcing-failure rejection must not RETIRE a real hazard: the claim
        # may be true with better citations, and its scenes must never flip to
        # "No known issue" silently (run 5: a fair CSATF-titles rejection took
        # a 110mph missing-door drive dark). Demote to the desk's open
        # questions — an honest unknown, on the record.
        entries = demotion_entries(dropped)
        oq_delta = {k: list(state.get(k) or []) + v for k, v in entries.items()}
        demoted = sum(len(v) for v in entries.values())
        if demoted:
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=f"⚖ {demoted} sourcing-failure rejection(s) demoted to open "
                            "questions — claims not disproven stay on the record"
                        )
                    ],
                ),
            )

        # The rating panel's rationale and cut list must describe the POST-
        # verification finding set, not the desk's pre-verification one.
        rating_delta: dict[str, Any] = {}
        pred = state.get("rating_prediction")
        if pred and dropped:
            revised = await self._reconcile_rating(client, pred, kept, dropped, sem)
            # run-13 item 2: the reconcile rewrites the cut list POST-filing, so
            # the filing gate never sees it. Scrub rule-shaped clauses from each
            # beat — the action survives, the justification dies; a beat the
            # scrub cannot cleanly fix ships UNMODIFIED and is manifest-recorded
            # (fail visible, never mangle silently).
            if revised is not None and revised.get("beats_to_cut"):
                scrubbed, misses = _scrub_cutlist(revised["beats_to_cut"])
                revised["beats_to_cut"] = scrubbed
                for beat, matched in misses:
                    manifest.append(
                        {
                            "guard": "normative_cutlist_scrub",
                            "stage": "post_reconcile",
                            "outcome": "unstripped",
                            "matched": matched,
                            "beat": beat[:120],
                        }
                    )
            if revised is not None and (
                revised["rationale"] != pred.get("rationale")
                or revised["beats_to_cut"] != (pred.get("beats_to_cut") or [])
            ):
                rating_delta["rating_prediction"] = {
                    **pred,
                    **revised,
                    "reconciled_after_verification": True,
                    "pre_verification": {
                        "rationale": pred.get("rationale"),
                        "beats_to_cut": pred.get("beats_to_cut"),
                    },
                }
                yield Event(
                    invocation_id=ctx.invocation_id,
                    author=self.name,
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                text="⚖ rating rationale/cut list reconciled with "
                                f"{len(dropped)} rejected finding(s)"
                            )
                        ],
                    ),
                )

        rejected = [
            fid for fid, v in verdicts.items() if ":" not in fid and v["verdict"] == "UNSUPPORTED"
        ]
        # count each FLAG once: the ":resourced" duplicates made supported +
        # partial + rejected exceed the number of flags verified
        base = {fid: v for fid, v in verdicts.items() if ":" not in fid}
        summary = (
            f"Verified {len(flags)} flags: "
            f"{sum(v['verdict'] == 'SUPPORTED' for v in base.values())} supported, "
            f"{sum(v['verdict'] == 'PARTIAL' for v in base.values())} partial, "
            f"{len(rejected)} rejected" + (f" ({', '.join(rejected)})" if rejected else "") + "."
        )
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(
                state_delta={
                    **{f"verdicts:{fid}": v for fid, v in verdicts.items()},
                    "verified_flags": kept,
                    "rejected_flags": dropped,
                    "guard_manifest:verification": manifest,
                    "resource_stats": resourced_stats,
                    # compact context for the Adjudicator's consistency pass —
                    # it must see WHY things were rejected, not the full flags
                    "rejected_summary": "\n".join(
                        f"- {r['flag_id']} ({r.get('category', '')}): "
                        f"{str(r.get('finding', ''))[:160]} | REJECTED: "
                        f"{str(r.get('rejection_reason', ''))[:200]}"
                        for r in dropped
                    )
                    or "(none)",
                    **oq_delta,
                    **rating_delta,
                }
            ),
            content=types.Content(role="model", parts=[types.Part(text=summary)]),
        )


agent = VerificationPanel(
    name="verification_panel",
    description="Blinded per-flag citation verification; can reject flags.",
)

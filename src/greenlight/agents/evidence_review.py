"""Bounded repair of compound claims, with independent verification before use.

Only judgement/text crosses the model boundary. Identity, citations and coordinates
stay fixed; estimates for a changed remedy become unknown rather than stale totals.
The verdict carries the audit trail without extending the public flag schema.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from google.genai import types
from pydantic import BaseModel, Field

from greenlight.agents.evidence import (
    PREQUALIFICATION_EVIDENCE,
    PRODUCTION_EVIDENCE,
    RATINGS_EVIDENCE,
    RESPONSE_OPTIONS,
)
from greenlight.agents.quote_anchor import anchor_quote
from greenlight.agents.source_rules import SourceBoundRepair, available_rules, bound_correction
from greenlight.contracts import validate
from greenlight.models import FLASH_MODEL

AUDIT_VERSION = 3


class SupportSpan(BaseModel):
    citation_number: int = Field(ge=1)
    quote: str = Field(min_length=1)


class EntailmentCheck(BaseModel):
    check_index: int
    entailed: bool
    reason: str
    scope_preserved: bool
    requirements_supported: bool
    scope_reason: str = Field(min_length=1)
    named_rights_status: Literal[
        "not_asserted", "qualified_attribution_or_lead", "unqualified_relationship"
    ]
    unsupported_parts: list[str] = Field(default_factory=list)


class EntailmentResult(BaseModel):
    checks: list[EntailmentCheck]


# The only unsupported-by-a-source remedy we can accept mechanically: gathering
# input facts, with no embedded obligation, specialist, equipment or method advice.
PRODUCTION_INQUIRY = (
    "Confirm casting, filming jurisdiction and staging method before specifying "
    "production requirements."
)


class ClaimCheck(BaseModel):
    field: Literal["finding", "remedy", "severity", "est_cost_usd", "est_added_days"]
    quote: str = Field(min_length=1)
    basis: Literal[
        "script",
        "production",
        "source",
        "planning",
        "application",
        "script_edit",
        "production_option",
        "inquiry",
        "risk_assessment",
        "estimate",
    ]
    status: Literal["SUPPORTED", "UNSUPPORTED", "UNKNOWN"]
    reason: str
    citation_numbers: list[int]
    support_spans: list[SupportSpan]
    script_spans: list[str] = Field(default_factory=list)


CLAIM_CHECK_INSTRUCTIONS = (
    PREQUALIFICATION_EVIDENCE
    + "\n"
    + RESPONSE_OPTIONS
    + "\n"
    + """\
Return claim_checks covering EVERY material assertion in BOTH finding and remedy,
plus the severity. Use a separate check for each asserted obligation or production
fact; one supported precaution cannot support the entire paragraph. quote is an exact
substring of that field (for severity, quote the level itself). For remedy quotes
use the detail prose only, excluding the action label. basis distinguishes script
facts, production facts, outside-world source claims, and planning advice.
Use basis=risk_assessment for a potential consequence justified by a cited rule and
actual screenplay trigger, with unknown applicability kept conditional. Include both
script_spans and support_spans. Missing final ownership or staging does not disprove
such an assessment. Distinguish it from asserting a specific owner, fee or requirement.
Use basis=application for applying a sourced rule to a screenplay fact or an explicitly
conditional production choice. Use basis=script for a pure scene observation, with
exact script_spans even when no source is needed. Use basis=production_option for the
high-level hazard-removal option defined above, with script_spans and support_spans
establishing the depicted event and hazard. Use basis=script_edit ONLY for a proposed change to
on-screen content that removes/reduces a cited trigger, not for equipment, specialists,
permits or rightsholder assertions. Such an edit need not be prescribed verbatim by
the source; the source must establish the trigger/rule and the edit must address it.
Never promise clearance, permission, safety or a final rating from a proposed edit.
For application/script_edit/production_option/risk_assessment include script_spans:
EXACT substrings of supplied SCENE TEXT anchoring the relevant content. They cannot
assert production facts. Separate
pure rule assertions from script facts when possible; don't demand that sources name
fictional characters, dialogue or props. A sourced ownership link still needs a source;
it cannot be inferred from a name in the script or the label's corporate parent.
A historical judgment or credit establishes ownership at that time; it does not alone
prove current ownership or authority for the requested use. Keep historical leads
qualified and distinguish document date from retrieval date.
For every source/planning/application/script_edit/production_option/risk_assessment
claim (except severity), and every remedy prescription,
provide support_spans: citation_number plus an EXACT verbatim quote from that numbered
excerpt. citation_numbers must match the receipt indexes. Choose the operative clause,
not the title, index listing, URL or scope heading. Do not quote from the whole document
from memory: only the supplied excerpt is available. Text merely being present does
not mean it entails the claim. Match the action, object, force and conditions:
- maintaining firearms-related LICENSES does not establish maintaining or controlling
  FIREARMS; do not substitute one object for the other;
- a minor's entitlement to a stunt double does not prescribe water/fire specialists,
  studio teachers, PPE or working hours;
- compliance with applicable laws does not establish a particular permit or authority;
- a guideline's title/scope does not establish its operative safety procedures.
Split compound prescriptions into separate checks. Check each duty, piece of equipment,
specialist, permit and condition independently, even within one sentence. A span for
one does not cover its neighbors. Do not call an unsourced prescription 'standard
practice', 'planning', or 'advice' to approve it. Recommendations also need evidence.
Without support for the rule/trigger mark that claim UNKNOWN/UNSUPPORTED with empty support_spans.
Script/production facts and severity judgement may have empty spans. Never transfer
an attribute from a fictional character to a performer, or from a depicted effect
to a practical shoot.
Check conditions independently in the remedy: 'if cast with a minor' in the finding
does NOT qualify an unconditional studio-teacher or permit requirement in the remedy.
General compliance language does not establish permits from specific authorities.
Planning advice must distinguish a recommendation from a mandatory requirement.
Mark unknown casting, jurisdiction or method asserted as fact UNKNOWN, even if a
safe production could plausibly choose it. SUPPORTED requires every material prose check
SUPPORTED. Unsupported standalone numeric estimates may be withheld separately.
"""
)

CLAIM_CHECK_INSTRUCTIONS += """
Audit each non-null structured estimate even when absent from the prose. For field
est_cost_usd use its canonical JSON array as quote (e.g. [5000,15000]); for field
est_added_days use its JSON number (e.g. 2). Use basis=estimate and support_spans for
the applicable rate/quote or comparable data, with quantities and assumptions explained
in the remedy. A range is not its own evidence. Zero days needs support too. Missing
or inapplicable numeric evidence is UNKNOWN; it does not invalidate a supported risk
assessment when those numbers can simply be withheld. Unsupported numbers asserted
in the prose must still be corrected. Do not require cost/day checks for null values.
"""


ESTIMATE_FIELDS = frozenset({"est_cost_usd", "est_added_days"})


def audit_fields(flag: dict[str, Any]) -> dict[str, str]:
    """Canonical audit surface, including numbers that never occur in prose."""
    return {
        "finding": flag["finding"],
        "remedy": flag["remedy"]["detail"],
        "severity": flag["severity"],
        **{
            key: json.dumps(flag["remedy"][key], separators=(",", ":"))
            for key in sorted(ESTIMATE_FIELDS)
            if flag["remedy"].get(key) is not None
        },
    }


def _summarize_checks(verdict: dict[str, Any]) -> dict[str, Any]:
    """Withhold unsupported numeric fields without erasing a supported concern."""
    bad = [c for c in verdict["claim_checks"] if c["status"] != "SUPPORTED"]
    result = dict(verdict)
    result["estimate_exclusions"] = sorted(
        {c["field"] for c in bad if c["field"] in ESTIMATE_FIELDS}
    )
    material = [c for c in bad if c["field"] not in ESTIMATE_FIELDS]
    if material and verdict["verdict"] in {"SUPPORTED", "PARTIAL"}:
        result.update(
            verdict="PARTIAL",
            reason="Claim audit requires correction: " + "; ".join(c["reason"] for c in material),
        )
    elif (
        bad
        and not material
        and verdict["verdict"] == "PARTIAL"
        and verdict.get("failure_mode", "none") == "none"
        and not verdict.get("fail_open")
        and not verdict.get("content_filtered")
    ):
        result.update(
            verdict="SUPPORTED", reason="Risk assessment supported; unverified estimates withheld"
        )
    return result


CLAIM_CHECK_INSTRUCTIONS += """
Use basis=inquiry ONLY for questions requesting missing input or a user decision
relevant to this desk and finding. No external support is required for the question;
it must not smuggle in an obligation, an unconfirmed factual premise or a prescription.
Ratings questions concern target/content decisions; clearance questions concern intended
use, permission status and ownership evidence; territory questions concern distribution
markets/version; safety questions concern casting, method and shooting jurisdiction.
Do not replace a supported useful remedy with a generic question. Production casting
questions cannot repair rating, copyright or distribution findings. Judge relevance
and usefulness as well as entailment. Do not relabel prescriptions as inquiries.
Check that the remedy action matches the detail: CUT/REPLACE for content edits,
OBTAIN_LICENSE/OBTAIN_RELEASE only with supported permission requirements,
ADD_SPECIALIST only for sourced specialist work. NO_ACTION may accompany an unresolved
input question; it must not disguise a content edit or mandatory production work.
"""


def _support_problem(  # noqa: PLR0912 - independent provenance boundaries
    check: ClaimCheck, flag: dict[str, Any], script_context: str
) -> str | None:
    """Validate provenance and anchor display quotes back to immutable raw sources."""
    if check.field == "severity":
        return None  # field, not a model-chosen basis, defines this judgement
    if check.basis == "inquiry" and check.field != "remedy":
        return "An inquiry must be a remedy question, not an asserted finding"
    if (
        check.field == "remedy"
        and check.quote == PRODUCTION_INQUIRY
        and flag.get("agent") != "safety_underwriter"
    ):
        return "Production-input inquiry is irrelevant to this desk"
    citations = flag["citations"]
    if check.field in ESTIMATE_FIELDS and (
        check.basis != "estimate" or check.quote != audit_fields(flag)[check.field]
    ):
        return "Numeric fields require a separate check of the complete canonical value"
    if check.basis in {"script_edit", "production_option"} and check.field != "remedy":
        return "A proposed edit or production option belongs in the remedy"
    if (
        check.basis in {"application", "script_edit", "production_option", "risk_assessment"}
        and not check.script_spans
        and check.field != "finding"
    ):
        return "An application or edit needs exact screenplay evidence"
    if any(not s.strip() or s not in script_context for s in check.script_spans):
        return "Script evidence is not verbatim in the supplied scene text"
    needs_span = (
        check.basis
        in {
            "source",
            "planning",
            "application",
            "script_edit",
            "production_option",
            "risk_assessment",
            "estimate",
        }
        and check.field != "severity"
    )
    needs_span |= check.field == "remedy" and check.basis != "inquiry"
    # Finding roles are determined independently, not by the first auditor's
    # label. Source/script facts need their corresponding receipts; statements
    # about the absence of a production brief need neither. All positive finding
    # checks go to the second reviewer, including those with empty receipts.
    if needs_span and not check.support_spans and check.field != "finding":
        return "No exact supporting span for this external claim or prescription"
    indexes = {span.citation_number for span in check.support_spans}
    if not check.support_spans and indexes != set(check.citation_numbers):
        return "Citation indexes and supporting spans do not match"
    anchored = []
    for span in check.support_spans:
        if span.citation_number > len(citations):
            return "Supporting span references a nonexistent citation"
        excerpt = citations[span.citation_number - 1].get("excerpt") or ""
        quote = anchor_quote(span.quote, excerpt)
        if quote is None:
            return "Supporting span is not verbatim in the cited excerpt"
        anchored.append(quote)
    # Apply only after every receipt passes; citations themselves never change.
    for span, quote in zip(check.support_spans, anchored, strict=True):
        span.quote = quote
    # The quoted receipts are authoritative. Repair this redundant index list
    # only after every receipt validates; never invent a span for an extra index.
    check.citation_numbers = sorted(indexes)
    return None


def _cover_clause_joins(body: str, covered: list[bool]) -> None:
    """Allow conjunctions between audited clauses, never omitted substantive text."""
    coverage = "".join("1" if hit else "0" for hit in covered)
    for gap in re.finditer("0+", coverage):
        start, end = gap.span()
        if (
            start > 0
            and end < len(body)
            and re.fullmatch(r"[\W_]*(?:and(?:\s+that)?|or|and/or)[\W_]*", body[start:end])
        ):
            covered[start:end] = [True] * (end - start)


def checked_verdict(
    verdict: dict[str, Any], flag: dict[str, Any], script_context: str = ""
) -> dict[str, Any]:
    """Validate the audit's anchors; a positive label cannot override failed clauses."""
    checks = [ClaimCheck.model_validate(c) for c in verdict["claim_checks"]]
    if not {"finding", "remedy", "severity"}.issubset({c.field for c in checks}):
        raise ValueError("claim audit must cover finding, remedy and severity")
    fields = audit_fields(flag)
    reanchors = []
    index_reanchors = []
    for check_index, check in enumerate(checks):
        if check.field not in fields or check.quote not in fields[check.field]:
            raise ValueError("claim audit quote is not in its field")
        if check.status == "SUPPORTED":
            submitted = [s.quote for s in check.support_spans]
            submitted_indexes = list(check.citation_numbers)
            problem = _support_problem(check, flag, script_context)
            if not problem and submitted_indexes != check.citation_numbers:
                index_reanchors.append(
                    {
                        "check_index": check_index,
                        "submitted_indexes": submitted_indexes,
                        "receipt_indexes": list(check.citation_numbers),
                    }
                )
            reanchors.extend(
                {
                    "check_index": check_index,
                    "span_index": span_index,
                    "citation_number": span.citation_number,
                    "submitted_quote": before,
                    "raw_quote": span.quote,
                }
                for span_index, (before, span) in enumerate(
                    zip(submitted, check.support_spans, strict=True)
                )
                if before != span.quote
            )
            if problem:
                check.status = "UNKNOWN"
                check.reason = problem + ". Original assessment: " + check.reason
    # A correct receipt for one sentence cannot hide an unaudited tail. This is
    # coverage, not semantic parsing: atomicity/entailment still need judgement.
    for field, body in fields.items():
        covered = [False] * len(body)
        if field == "finding" and (prefix := re.match(r"\[partially supported\]\s*", body)):
            covered[: prefix.end()] = [True] * prefix.end()
        for check in checks:
            if check.field != field:
                continue
            start = body.find(check.quote)
            while start != -1:
                covered[start : start + len(check.quote)] = [True] * len(check.quote)
                start = body.find(check.quote, start + len(check.quote))
        # Atomic checks commonly omit a conjunction between two audited clauses.
        # Internal joins are reviewed in the complete claim context downstream;
        # never swallow an unaudited clause, exception, condition or negation.
        _cover_clause_joins(body, covered)
        gaps = [i for i, char in enumerate(body) if char.isalnum() and not covered[i]]
        if gaps:
            checks.append(
                ClaimCheck(
                    field=field,
                    quote=body[gaps[0] : gaps[-1] + 1],
                    basis="source",
                    status="UNKNOWN",
                    reason="Material text was omitted from the claim audit",
                    citation_numbers=[],
                    support_spans=[],
                )
            )
    verdict = {
        **verdict,
        "claim_checks": [c.model_dump() for c in checks],
        "support_span_version": AUDIT_VERSION,
        "audit_input": flag_fingerprint(flag),
        **({"support_span_reanchors": reanchors} if reanchors else {}),
        **({"citation_index_reanchors": index_reanchors} if index_reanchors else {}),
    }
    return _summarize_checks(verdict)


def flag_fingerprint(flag: dict[str, Any]) -> str:
    """Bind a repair to the exact claim, remedy, sources and coordinates reviewed."""
    fields = {
        k: flag.get(k)
        for k in (
            "flag_id",
            "agent",
            "scene_ids",
            "category",
            "finding",
            "remedy",
            "citations",
            "severity",
        )
    }
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def apply_estimate_audit(flag: dict[str, Any], verdict: dict[str, Any]) -> dict[str, Any]:
    """A new audit cannot deliver an unreviewed number; old records stay unchanged."""
    if verdict.get("support_span_version", 0) < AUDIT_VERSION:
        return flag
    if verdict.get("audit_input") != flag_fingerprint(flag):
        raise ValueError("claim audit does not match the reviewed finding")
    excluded = set(verdict.get("estimate_exclusions", []))
    for field in ESTIMATE_FIELDS:
        checks = [c for c in verdict["claim_checks"] if c["field"] == field]
        if not checks or any(c["status"] != "SUPPORTED" for c in checks):
            excluded.add(field)
    return {
        **flag,
        "remedy": {**flag["remedy"], **{k: None for k in sorted(excluded & ESTIMATE_FIELDS)}},
    }


def present_corpus_statistics(flag: dict, verdict: dict) -> tuple[dict, list[dict]]:
    """Move independently audited corpus sentences to their existing citation/card.

    Never strip arbitrary numbers, scene facts, prescriptions or partial clauses.
    Called after the positive audit's input binding has been checked. The original
    audited text and exact replacement remain in verdict metadata.
    """
    if verdict.get("support_span_version", 0) < AUDIT_VERSION or not str(
        flag.get("category", "")
    ).startswith("rating_"):
        return flag, []
    statistic = re.compile(r"\d\s*%|\bn\s*=\s*\d")
    source = (flag.get("marginal") or {}).get("source")
    bodies = {"finding": flag["finding"], "remedy": flag["remedy"]["detail"]}
    edits = []
    reviewed = {
        c["check_index"]
        for c in verdict.get("entailment_review", {}).get("checks", [])
        if c.get("entailed")
        and c.get("scope_preserved")
        and c.get("requirements_supported")
        and not c.get("unsupported_parts")
    }
    for index, check in enumerate(verdict.get("claim_checks", [])):
        field, quote = check["field"], check["quote"]
        if (
            field not in bodies
            or not statistic.search(quote)
            or check["status"] != "SUPPORTED"
            or check["basis"] != "source"
            or check.get("script_spans")
            or index not in reviewed
            or not source
            or not check.get("support_spans")
        ):
            continue
        citations = [flag["citations"][s["citation_number"] - 1] for s in check["support_spans"]]
        if any(
            c.get("via") != "local"
            or c.get("source_type") != "rules_table"
            or c.get("title") != source
            for c in citations
        ):
            continue
        body = bodies[field]
        if body.count(quote) != 1 or quote[-1:] not in {".", "!", "?"}:
            continue
        before, after = body.split(quote)
        if before.strip() and before.rstrip()[-1] not in ".!?":
            continue  # cannot cut a subordinate clause away from its condition
        replacement = (
            "Corpus figures describe rationales for released films; see the cited distribution."
        )
        bodies[field] = before + replacement + after
        edits.append(
            {
                "field": field,
                "original_quote": quote,
                "replacement": replacement,
                "citation_numbers": check["citation_numbers"],
            }
        )
    if any(statistic.search(body) for body in bodies.values()):
        raise ValueError("rating statistics were not isolated as independently audited corpus text")
    return {
        **flag,
        "finding": bodies["finding"],
        "remedy": {**flag["remedy"], "detail": bodies["remedy"]},
    }, edits


class CorrectedClaim(BaseModel):
    finding: str = Field(min_length=1, max_length=4000)
    remedy_detail: str = Field(min_length=1, max_length=4000)
    remedy_action: Literal[
        "REPLACE",
        "OBTAIN_LICENSE",
        "OBTAIN_RELEASE",
        "RESHOOT",
        "ADD_DISCLAIMER",
        "ADD_SPECIALIST",
        "CUT",
        "NO_ACTION",
    ]
    severity: Literal["BLOCKER", "HIGH", "MEDIUM", "LOW", "FYI"]


def corrected_flag(flag: dict[str, Any], correction: dict[str, Any]) -> dict[str, Any]:
    """Apply only reviewed text/action/severity; discard superseded estimates."""
    patch = CorrectedClaim.model_validate(correction)
    if not patch.finding.strip() or not patch.remedy_detail.strip():
        raise ValueError("empty correction")
    mentioned = set(re.findall(r"\bS\d{3,4}\b", patch.finding + " " + patch.remedy_detail))
    if mentioned - set(flag["scene_ids"]):
        raise ValueError("repair names a scene outside the reviewed coordinates")
    new = {
        **flag,
        "finding": patch.finding.strip(),
        "severity": patch.severity,
        "remedy": {
            "action": patch.remedy_action,
            "detail": patch.remedy_detail.strip(),
            "est_cost_usd": None,
            "est_added_days": None,
        },
    }
    # Rejections and transient markers belong to the superseded version.
    for key in (
        "rejection_reason",
        "failure_mode",
        "recoverable",
        "verification_unavailable",
        "verification_blocked",
        "cost_excluded_on_target_path",
    ):
        new.pop(key, None)
    return validate("flag", new)


def unresolved_verdict(original: dict[str, Any], reason: str, **trail: Any) -> dict[str, Any]:
    return {
        "verdict": "UNSUPPORTED",
        "failure_mode": "premise_unsupported",
        "reason": "Evidence correction unresolved: " + reason,
        "evidence_review_unresolved": True,
        "evidence_review": {"before": original, **trail},
    }


async def check_entailment(client, flag, verdict):
    """One narrow independent batch: can these exact spans support these claims?

    Only exact scene receipts accompany rule applications/edits; no previous
    reasoning or severity is shown. Script evidence cannot supply external duties.
    Full excerpt context prevents a receipt from hiding a negation or exception.
    Source metadata identifies attribution; it cannot supply an operative rule.
    """
    if verdict["verdict"] not in {"SUPPORTED", "PARTIAL"}:
        return verdict
    claims = []
    for index, check in enumerate(verdict["claim_checks"]):
        if check["status"] != "SUPPORTED":
            continue  # review the claimed positives before repair can inherit them
        # Severity is a judgement made by the script-aware audit. A model may
        # attach receipts voluntarily; that must not turn HIGH into a purported
        # verbatim source assertion for this intentionally script-blind review.
        fixed_safety_inquiry = (
            check["basis"] == "inquiry"
            and check["quote"] == PRODUCTION_INQUIRY
            and flag.get("agent") == "safety_underwriter"
        )
        if check["field"] == "severity" or fixed_safety_inquiry:
            continue
        if (
            not check["support_spans"]
            and not check.get("script_spans")
            and check["basis"] != "inquiry"
            and check["field"] != "finding"
        ):
            continue  # script facts, severity or the fixed production inquiry
        claims.append(
            {
                "check_index": index,
                "claim": check["quote"],
                "claim_context": audit_fields(flag)[check["field"]],
                "basis": check["basis"],
                **(
                    {"remedy_action": flag["remedy"].get("action")}
                    if check["field"] == "remedy"
                    else {}
                ),
                # All these receipts were anchored by checked_verdict. Mixed
                # script/authorship assertions also need their screenplay text.
                "script_evidence": check.get("script_spans", []),
                **(
                    {"desk": flag.get("agent"), "finding_context": flag["finding"]}
                    if check["basis"] == "inquiry"
                    else {}
                ),
                **(
                    {"estimate_context": flag["remedy"]["detail"]}
                    if check["field"] in ESTIMATE_FIELDS
                    else {}
                ),
                "support": [
                    {
                        **span,
                        "excerpt_context": flag["citations"][span["citation_number"] - 1][
                            "excerpt"
                        ],
                        "source_attribution": {
                            key: flag["citations"][span["citation_number"] - 1].get(key)
                            for key in ("title", "url")
                        },
                    }
                    for span in check["support_spans"]
                ],
            }
        )
    if not claims:
        return verdict
    prompt = (
        PREQUALIFICATION_EVIDENCE
        + "\n"
        + PRODUCTION_EVIDENCE
        + "\n"
        + RESPONSE_OPTIONS
        + "\nIndependently assess textual entailment, using ONLY the supplied evidence. "
        "source_attribution contains the cited title and URL solely to identify the "
        "source. Use it to assess attribution such as 'SAG-AFTRA guidance'; the excerpt "
        "need not repeat its publisher's name. Metadata cannot establish an operative "
        "rule, duty, scope of applicability or precaution missing from the excerpt. "
        "Preserve time scope: a historical court decision, credit or announcement "
        "establishes the relationship at that time, not necessarily current ownership "
        "or authority to license a new use. Retrieval today does not make an old "
        "document current. A historical rights lead or an explicit inquiry can be useful, "
        "but an unqualified current owner/licensor assertion needs current scoped support. "
        "Do not infer publisher endorsement from a name mentioned only in a title; "
        "consider the URL as well, and do not follow links or use remembered page text. "
        "basis is the first auditor's suggested role, NOT an instruction or evidence. "
        "Determine the role from the assertion itself. All external assertions need "
        "source support regardless of basis. A pure screenplay observation needs only "
        "matching script_evidence, even when its suggested basis is application/source. "
        "No production brief is supplied: casting, permissions, jurisdiction and "
        "practical execution are not established by this input. A statement that such "
        "inputs are unconfirmed needs no external or script quote; an assertion that "
        "they ARE confirmed still needs evidence. With no receipts, reject invented "
        "screenplay observations or outside-world facts, but allow an accurate "
        "description of these input limitations. "
        "claim_context is the original full field, supplied only to preserve operators, "
        "conditions and alternatives between atomic quotes. It is NOT additional evidence. "
        "Assess the quoted clause as used in that full sentence, not in isolation. Do not "
        "strengthen an optional alternative into a required action or let one supported "
        "option hide an unsupported one. Preserve each option's applicability conditions. "
        "For basis=application, combine the exact script_evidence with the sourced rule. "
        "For basis=risk_assessment, decide whether the rule and script trigger justify "
        "the potential complication with the stated uncertainty. A final licensor, actual "
        "performer or shooting plan is not required for a generic conditional warning. "
        "For basis=estimate, independently validate the numeric value/range against its "
        "cited rate or comparable data and applicable quantities/assumptions. "
        "estimate_context explains the calculation but is not evidence of a rate. "
        "Script evidence establishes only fictional content, not permits, real casting, "
        "shooting jurisdiction, practical method, ownership or permission. Sources need "
        "not name screenplay characters or dialogue. Retain conditions on unknown facts. "
        "For basis=script_edit, verify that the proposed on-screen change addresses a "
        "trigger established by the source and present in script_evidence. The source "
        "need not literally instruct an editor or name replacement dialogue. Reject "
        "guaranteed clearance, permission, safety or rating outcomes; an edit addressing "
        "one issue does not establish resolution of all issues. Do not accept new "
        "equipment, specialist, permit, labor or ownership assertions as script edits. "
        "Replacement labels alone do not establish permission to use replacement assets. "
        "For a production_option, apply the same trigger-removal test to a proposed "
        "physical staging choice under RESPONSE OPTIONS, even if it was mislabelled "
        "script_edit or planning. No source-prescribed technique is required for a "
        "high-level proposal to omit the hazard; new procedures still need support. "
        "For basis=inquiry, check that it only requests relevant missing input or a "
        "user decision for the supplied desk/finding. Reject irrelevant generic casting "
        "questions on rating/clearance/territory findings, concealed prescriptions or "
        "unconfirmed factual premises. finding_context is context for relevance only, "
        "not evidence that its assertions are true. "
        "When remedy_action is supplied, reject a CUT/REPLACE edit or mandatory "
        "production work labelled NO_ACTION; an unresolved input question may use it. "
        "For each check_index decide whether the evidence establishes the claim or "
        "justifies the conditional edit/inquiry under these rules. Do not use industry knowledge "
        "or the plausibility of precautions. Titles, scope headings and index entries "
        "cannot establish an operative requirement. A general duty to obey applicable "
        "laws does not establish named permits, specialists or equipment. Maintaining "
        "licenses is not maintaining/control of firearms. Entitlement to a stunt double "
        "does not prescribe other specialists, PPE or labor obligations. A recommendation "
        "for production work is not exempt: 'should', 'consider' and 'standard planning' "
        "still require source support for the prescribed precaution. High-level hazard "
        "removal options follow RESPONSE OPTIONS; they are not operating procedures. Evaluate EACH "
        "duty/object/condition in a compound "
        "claim; if ANY is unsupported, entailed=false and name the unsupported part. "
        "Do not strengthen 'may' into 'must', omit an exception, or approve a quote that "
        "is negated by its context. Reasonable application to a stated hypothetical is "
        "allowed only if the source actually supplies that rule or safeguard. Never "
        "treat a nearby related topic as entailment. Return every check_index exactly "
        "once. In addition to entailed, separately answer scope_preserved and "
        "requirements_supported, and give scope_reason. List every unsupported "
        "assertion/condition in unsupported_parts (empty only if all pass). "
        "Test the scope counterfactually: for EACH alternative triggering condition, "
        "would this source establish the rule if ONLY that alternative occurred? "
        "Script evidence satisfying one branch cannot justify another branch. Compare "
        "source trigger, exclusions and 'as applicable' qualifications against the claim. "
        "Check every named duty/owner/amount separately from the risk assessment. "
        "Return named_rights_status for EACH check. Use not_asserted when no named "
        "ownership/licensing relationship is asserted (a generic rights holder or "
        "administrator role is not a named party). Use qualified_attribution_or_lead "
        "only for explicit source attribution, date-qualified historical relationships "
        "or a lead whose current authority is to be confirmed. Use "
        "unqualified_relationship for an asserted named owner, controller or licensor "
        "for this production, including a company in parentheses after 'owner' and "
        "instructions to obtain rights from a named company. Merely citing a source "
        "does not qualify the assertion. A copyright/phonogram credit, even on a "
        "current catalog page, is an attribution, not confirmation of licensing "
        "authority for this use. Our pre-qualification output must preserve that "
        "distinction; unqualified_relationship cannot pass. Authorship and the "
        "screenplay's recording/label description alone do not assert rights ownership. "
        "For an inquiry, script edit or production option, scope_preserved means it "
        "addresses this issue "
        "and requirements_supported means it introduces no unsupported duty or guarantee. "
        "Any failed component must set entailed=false.\n\n" + json.dumps(claims)
    )
    try:
        response = await client.aio.models.generate_content(
            model=FLASH_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EntailmentResult,
                temperature=0.0,
            ),
        )
        result = EntailmentResult.model_validate_json(response.text)
        wanted = {claim["check_index"] for claim in claims}
        got = [check.check_index for check in result.checks]
        if len(got) != len(set(got)) or set(got) != wanted:
            raise ValueError("entailment review omitted, repeated or invented a check")
    except Exception as exc:
        return unresolved_verdict(
            verdict, f"span entailment review unavailable ({type(exc).__name__})"
        )
    checks = [dict(c) for c in verdict["claim_checks"]]
    for result_check in result.checks:
        if not result_check.scope_reason.strip():
            return unresolved_verdict(
                verdict, "independent review omitted scope or requirement checks"
            )
        if (
            not result_check.entailed
            or result_check.scope_preserved is False
            or result_check.requirements_supported is False
            or result_check.unsupported_parts
            or result_check.named_rights_status == "unqualified_relationship"
        ):
            result_check.entailed = False
            checks[result_check.check_index] = {
                **checks[result_check.check_index],
                "status": "UNSUPPORTED",
                "reason": "Independent span review: "
                + "; ".join(
                    part
                    for part in (
                        result_check.reason,
                        result_check.scope_reason,
                        "Named rights relationships must remain source attributions or "
                        "leads pending confirmation of authority for the intended use"
                        if result_check.named_rights_status == "unqualified_relationship"
                        else "",
                        *result_check.unsupported_parts,
                    )
                    if part.strip()
                ),
            }
    return _summarize_checks(
        {
            **verdict,
            "claim_checks": checks,
            "entailment_review": result.model_dump(),
            "entailment_policy_version": 2,
        }
    )


def repair_evidence(flag: dict, verdict: dict) -> tuple[dict, dict]:
    """Construct from checked evidence instead of exposing rejected paragraphs again."""
    identity = {
        key: flag[key]
        for key in ("flag_id", "agent", "scene_ids", "category", "severity", "citations")
    }
    accepted, limitations = [], []
    bad_checks = [c for c in verdict.get("claim_checks", []) if c["status"] != "SUPPORTED"]
    for check in verdict.get("claim_checks", []):
        if check["status"] != "SUPPORTED":
            limitations.append({"field": check["field"], "reason": check["reason"]})
        elif check["field"] == "severity" or check["field"] in ESTIMATE_FIELDS:
            continue
        elif any(
            bad["field"] == check["field"] and bad["quote"] in check["quote"] for bad in bad_checks
        ):
            continue  # a broad positive cannot smuggle a known failed subclause into repair
        elif check["basis"] in {"script", "production"}:
            # A script-labelled paraphrase can contain extra remembered details
            # (e.g. release year). Give the generator the actual scene receipts.
            if spans := check.get("script_spans"):
                accepted.append({"basis": "script", "script_spans": spans})
        else:
            accepted.append(
                {
                    key: check.get(key, [])
                    for key in ("field", "quote", "basis", "support_spans", "script_spans")
                }
            )
    return identity, {"accepted_assertions": accepted, "limitations": limitations}


async def repair_partial(client, flag, context, search, original, verify_once):
    """One correction + one blinded check. No recursive repair or new retrieval."""
    # A censored verifier has not checked the script. It cannot approve a repair.
    if original.get("content_filtered"):
        return unresolved_verdict(original, "script verification was blocked")
    rules = available_rules(flag)
    identity, evidence = repair_evidence(flag, original)
    prompt = (
        PREQUALIFICATION_EVIDENCE
        + "\n"
        + PRODUCTION_EVIDENCE
        + "\n"
        + RATINGS_EVIDENCE
        + "\n"
        + RESPONSE_OPTIONS
        + "\nDESK: "
        + str(flag.get("agent"))
        + "\nKeep source rules, their application to verified screenplay facts, and proposed "
        "content edits distinct. A proposed CUT or REPLACE can remove a cited trigger "
        "without the source literally naming the scene or instructing an editor. Explain "
        "what the edit changes; do not promise a final rating, permission or clearance. "
        "Production duties, ownership, licenses and specialists still need operative "
        "source support. If necessary, ask only for missing input relevant to this desk "
        "and finding. Do not replace a useful supported edit with an unrelated question. "
        "Casting/method inquiries belong to safety, not to ratings, clearance or territory. "
        + "\nConstruct a new finding AND remedy from the accepted assertions, exact scene "
        "text and original source excerpts below. Rejected prose and the earlier summary "
        "are deliberately withheld; limitations explain what cannot be asserted. "
        "An excerpt's historical relationship may become a qualified inquiry lead, not "
        "a claim of current licensing authority. Preserve the supported "
        "hazard/exposure; remove unsupported obligations and qualify actual casting, method "
        "and jurisdiction assumptions in BOTH fields. Do not invent sources or requirements. "
        "Every external prescription needs an operative supporting span in the supplied "
        "citations. Removing 'must' or calling it planning advice does not fix absent support. "
        "A license-maintenance rule does not support firearms maintenance, and entitlement "
        "to a stunt double does not establish other specialists or equipment. "
        "Remove prescriptions whose action/object/conditions the excerpts do not establish. "
        "Do not add a release deadline, a phase such as 'before principal photography', "
        "a lead time, fee, equipment specification or assurance unless its exact "
        "requirement is supported by an operative supplied excerpt. Keep each sourced "
        "next step, proposed removal option and input question in a separate sentence "
        "with its own applicability condition. Prefer a concise supported remedy over "
        "adding speculative alternatives. "
        "If only a depicted safety hazard and unknown production facts remain, preserve "
        "the concern and ask what casting/method/jurisdiction is planned. Other desks "
        "must ask relevant missing-use, permission, distribution or content questions. "
        "Build the correction from the independently accepted observations and source "
        "rules. Do not preserve an owner, fee or requirement merely because it appeared "
        "in the original flag. With an unresolved owner, retain a generic licensing-risk "
        "assessment and a useful removal/replacement or rights-investigation option. "
        "Choose an action consistent with the remedy; do not put a content edit or "
        "mandatory production work under NO_ACTION. "
        "Review severity against the surviving hazard, not the removed assumptions; it may "
        "remain HIGH for a serious hazard. Costs and days will be withheld because the "
        "remedy changed. "
        + (
            "Return a finding containing only verified screenplay observations and relevant "
            "conditional risks, a severity, and the applicable rule_ids from SOURCE RULES. "
            "Do not restate external duties in the finding. Code will construct the remedy "
            "from the selected rules' exact wording; you cannot add or rewrite a requirement, "
            "condition, alternative, owner, amount or exception. Select only rules relevant "
            "to the depicted risk; missing production facts must remain conditional.\n"
            "SOURCE RULES:\n" + json.dumps(rules) + "\n"
            if rules
            else "Return the corrected finding, remedy_detail, remedy_action, severity. "
        )
        + "If no supported exposure remains, return an empty finding (repair will be refused).\n\n"
        + "FLAG:\n"
        + json.dumps(identity)
        + "\nVERIFICATION:\n"
        + json.dumps(evidence)
        + "\nSCENE TEXT:\n"
        + context
        + "\nFULL-SCRIPT SEARCH:\n"
        + search
    )
    try:
        res = await client.aio.models.generate_content(
            model=FLASH_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SourceBoundRepair if rules else CorrectedClaim,
                temperature=0.0,
            ),
        )
        selected_rules = []
        if rules:
            correction, selected_rules = bound_correction(
                SourceBoundRepair.model_validate_json(res.text), rules
            )
        else:
            correction = CorrectedClaim.model_validate_json(res.text).model_dump()
        candidate = corrected_flag(flag, correction)
        from greenlight.agents.verification import _refile_gate_problem

        gate = _refile_gate_problem(candidate, check_authority=False)
        if gate:
            return unresolved_verdict(original, gate, correction=correction)
        # Deliberately omit original reasoning/audit: the second check is blinded.
        after = await verify_once(client, candidate, context, search)
    except Exception as exc:
        return unresolved_verdict(original, f"repair/check unavailable ({type(exc).__name__})")
    if (
        after.get("verdict") != "SUPPORTED"
        or after.get("fail_open")
        or after.get("content_filtered")
    ):
        return unresolved_verdict(
            original,
            "corrected claim did not pass independent verification",
            correction=correction,
            after=after,
            source_rules=selected_rules,
        )
    return {
        **after,
        "evidence_review": {"before": original, "after": after, "source_rules": selected_rules},
        "correction": correction,
        "correction_input": flag_fingerprint(flag),
    }


def review_incomplete(verdicts: dict[str, Any]) -> bool:
    return any(
        v.get("evidence_review_unresolved")
        for fid, v in verdicts.items()
        if ":" not in fid and isinstance(v, dict)
    )

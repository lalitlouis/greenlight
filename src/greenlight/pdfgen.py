# ruff: noqa: PLR2004, PLR0915, RUF001 - canvas layout is coordinates and dashes
"""Real PDF downloads for the binder and one-sheet — no print dialog.

reportlab, deterministic, server-side. The binder is a landscape-letter
clearance log with a repeating header; the one-sheet is the dark poster.
"""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NAVY = colors.HexColor("#0c1524")
GOLD = colors.HexColor("#e8b64c")
CREAM = colors.HexColor("#f5f5f7")
INK = colors.HexColor("#1a1712")
FAINT = colors.HexColor("#8a8271")
SEV_COLORS = {
    "BLOCKER": colors.HexColor("#e0342a"),
    "HIGH": colors.HexColor("#e97c00"),
    "MEDIUM": colors.HexColor("#b08a00"),
    "LOW": colors.HexColor("#6e6e73"),
}

_CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=INK)
_CELL_DIM = ParagraphStyle("celld", parent=_CELL, textColor=FAINT)
_HEAD = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=FAINT)


def binder_pdf(data: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=0.45 * inch,
        rightMargin=0.45 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.45 * inch,
        title=f"{data['title']} — Clearance Log",
    )
    story: list[Any] = []
    title_style = ParagraphStyle("t", fontName="Times-Bold", fontSize=20, leading=24, textColor=INK)
    sub_style = ParagraphStyle("s", fontName="Helvetica", fontSize=8.5, textColor=FAINT)
    story.append(Paragraph(f"{data['title']} — Production Clearance Log", title_style))
    counts = data.get("counts") or {}
    tiers = ", ".join(
        f"{counts[t]} {t.lower()}"
        for t in ("BLOCKER", "HIGH", "MEDIUM", "LOW", "FYI")
        if counts.get(t)
    )
    story.append(
        Paragraph(
            f"Generated {data['generated_at']} · Greenlight Score "
            + (
                "WITHHELD (analysis incomplete)"
                if data.get("score") is None
                else f"{data.get('score')}/100"
            )
            + " (ordinal risk index, not a probability) · "
            f"{tiers} · prepared by ScriptRisk (scriptrisk.com)",
            sub_style,
        )
    )
    d = data.get("draft") or {}
    if d.get("sha256"):
        prov = (
            "script's own scene numbers"
            if d.get("scene_numbers") == "script"
            else "generated scene coordinates"
        )
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(
                f"This report is valid only for this draft: {d.get('pages', '?')} pp · "
                f"{prov} · SHA-256 {d['sha256'][:12]}…",
                sub_style,
            )
        )
    story.append(Spacer(1, 10))

    # Columns arrive pre-filtered (empty ones dropped server-side); widths are
    # keyed by identity so a dropped column redistributes to the remedy.
    cols = data["columns"]
    col_w = {
        "Scene": 0.8,
        "Page": 0.35,
        "Scene heading": 1.2,
        "Item": 1.0,
        "Category": 0.9,
        "Severity": 0.6,
        "Clearance status": 1.0,
        "Remedy / licensing note": 3.4,
        "Est. cost (USD)": 0.7,
        "Sources": 1.0,
        "Finding": 0.5,
    }
    fracs = [col_w.get(c, 1.0) for c in cols]
    page_w = landscape(letter)[0] - 0.9 * inch
    widths = [f / sum(fracs) * page_w for f in fracs]
    sev_col = cols.index("Severity") if "Severity" in cols else -1

    def _cell(text: str, style: ParagraphStyle) -> Paragraph:
        # reportlab Paragraph parses mini-XML — unescaped '&' corrupts cells
        import html as _html

        safe = _html.escape(str(text)).replace("\n", "<br/>")
        return Paragraph(safe, style)

    rows: list[list[Any]] = [[_cell(c.upper(), _HEAD) for c in cols]]
    styles_extra = []
    for i, r in enumerate(data["rows"], start=1):
        style = _CELL_DIM if r.get("Clearance status") == "No known issue" else _CELL
        rows.append([_cell(r.get(c, ""), style) for c in cols])
        sev = r.get("Severity")
        if sev in SEV_COLORS and sev_col >= 0:
            styles_extra.append(("TEXTCOLOR", (sev_col, i), (sev_col, i), SEV_COLORS[sev]))
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 1, INK),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor("#e5e0d2")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                *styles_extra,
            ]
        )
    )
    story.append(table)

    import html as _html

    sec_style = ParagraphStyle(
        "sec", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=INK, spaceBefore=14
    )
    item_style = ParagraphStyle("item", parent=_CELL, fontSize=8, leading=10.5)

    def _sec(title: str, items: list[str]) -> None:
        if not items:
            return
        story.append(Paragraph(_html.escape(title).upper(), sec_style))
        for it in items:
            story.append(Paragraph(_html.escape(it), item_style))

    bm = data.get("back_matter") or {}
    if bm.get("unexamined"):
        _sec(
            f"NOT EXAMINED — {len(bm['unexamined'])} extracted item(s) with no disposition",
            [
                "These items were found in the script but no desk flagged, cleared, or "
                "questioned them. Their scenes are NOT cleared. Rerun before relying on "
                "this binder.",
                *bm["unexamined"],
            ],
        )
    if bm.get("desks_incomplete"):
        _sec(
            "INCOMPLETE — desks with zero dispositions",
            [
                f"The {d} desk returned no dispositions for its worklist; its portion of this "
                "analysis is unexamined, not clear. Rerun before relying on this binder."
                for d in bm["desks_incomplete"]
            ],
        )
    rating = bm.get("rating") or {}
    if rating.get("predicted"):
        tgt = (
            f" · production target {rating['target']}"
            if rating.get("target") and rating["target"] != rating["predicted"]
            else ""
        )
        _sec("Rating prediction", [f"Predicted {rating['predicted']}{tgt}"])
    _sec(
        f"Reviewed & cleared ({len(bm.get('cleared') or [])})",
        [f"[{c['desk']}] {c['text']}" for c in bm.get("cleared") or []],
    )
    _sec(
        "Open questions — honest unknowns",
        [f"[{q['desk']}] {q['text']}" for q in bm.get("open_questions") or []],
    )
    _sec(
        f"Rejected in verification ({len(bm.get('rejected') or [])})",
        [f"{r['finding']} ({r['category']}): {r['reason']}" for r in bm.get("rejected") or []],
    )
    _sec("Adjudication", list(bm.get("adjudication") or []))
    _sec("Sources cited", [" · ".join(bm.get("sources") or [])] if bm.get("sources") else [])

    story.append(Spacer(1, 12))
    story.append(Paragraph(data.get("disclaimer", ""), sub_style))
    doc.build(story)
    return buf.getvalue()


def onesheet_pdf(record: dict[str, Any]) -> bytes:
    from reportlab.pdfgen import canvas as pdfcanvas

    buf = io.BytesIO()
    w, h = letter
    c = pdfcanvas.Canvas(buf, pagesize=letter)
    c.setTitle(f"{record.get('script_title', 'One-Sheet')} — ScriptRisk One-Sheet")
    c.setFillColor(NAVY)
    c.rect(0, 0, w, h, stroke=0, fill=1)

    rep = record.get("report") or {}
    counts = rep.get("counts") or {}
    score = rep.get("greenlight_score") or 0
    blockers = counts.get("BLOCKER", 0)
    margin = 0.75 * inch
    y = h - 1.0 * inch

    c.setFillColor(GOLD)
    c.circle(margin + 5, y + 4, 5, stroke=0, fill=1)
    c.setFont("Times-Bold", 15)
    c.setFillColor(CREAM)
    c.drawString(margin + 18, y, "SCRIPT")
    from reportlab.pdfbase.pdfmetrics import stringWidth

    c.setFillColor(colors.HexColor("#ff5f54"))
    c.drawString(margin + 18 + stringWidth("SCRIPT", "Times-Bold", 15), y, "RISK")
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(GOLD)
    c.drawRightString(w - margin, y, "PRODUCTION RISK ONE-SHEET")

    y -= 0.65 * inch
    c.setFont("Times-Bold", 30)
    c.setFillColor(CREAM)
    c.drawString(margin, y, (record.get("script_title") or "Untitled")[:38])

    # score ring
    ring_x, ring_y, ring_r = w - margin - 55, y - 20, 44
    tone = (
        SEV_COLORS["BLOCKER"]
        if blockers or score < 40
        else (SEV_COLORS["HIGH"] if score < 75 else colors.HexColor("#0e7c4a"))
    )
    c.setLineWidth(7)
    c.setStrokeColor(colors.HexColor("#22304a"))
    c.circle(ring_x, ring_y, ring_r, stroke=1, fill=0)
    c.setStrokeColor(tone)
    c.arc(
        ring_x - ring_r,
        ring_y - ring_r,
        ring_x + ring_r,
        ring_y + ring_r,
        90,
        -int(360 * min(100, score) / 100),
    )
    c.setFont("Times-Bold", 26)
    c.setFillColor(CREAM)
    c.drawCentredString(ring_x, ring_y - 8, str(score))
    c.setFont("Helvetica", 8)
    c.drawCentredString(ring_x, ring_y - 22, "/100")

    y -= 0.35 * inch
    verdict = (
        f"Not cleared — {blockers} blocker(s)"
        if blockers
        else ("Cleared, with conditions" if score >= 75 else "Conditional — remedies required")
    )
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(tone)
    c.drawString(margin, y, verdict)
    y -= 0.28 * inch
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#9aa3b2"))
    c.drawString(
        margin,
        y,
        f"{len(record.get('flags', []))} findings · "
        f"{len(record.get('rejected_flags', []))} rejected in verification · "
        f"{len(record.get('entities', []))} entities researched",
    )
    cost = rep.get("est_clearance_cost_usd")
    if cost and len(cost) == 2:
        y -= 0.26 * inch
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(CREAM)
        c.drawString(margin, y, f"Estimated clearance exposure ${cost[0]:,.0f}–${cost[1]:,.0f}")

    # desk scores
    y -= 0.55 * inch
    dims = rep.get("dimension_scores") or {}
    labels = [
        ("clearance_counsel", "Rights & Clearances", "#818cf8"),
        ("ratings_board", "Ratings", "#c084fc"),
        ("safety_underwriter", "Safety", "#fbbf24"),
        ("territory_censor", "Territories", "#38bdf8"),
    ]
    bw = (w - 2 * margin - 30) / 4
    for i, (key, label, color) in enumerate(labels):
        x = margin + i * (bw + 10)
        c.setStrokeColor(colors.HexColor(color))
        c.setLineWidth(2)
        c.line(x, y + 28, x + bw, y + 28)
        c.setStrokeColor(colors.HexColor("#22304a"))
        c.setLineWidth(0.8)
        c.roundRect(x, y - 22, bw, 50, 8, stroke=1, fill=0)
        c.setFont("Times-Bold", 19)
        c.setFillColor(CREAM)
        c.drawString(x + 12, y + 2, str(dims.get(key, "—")))
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#9aa3b2"))
        c.drawString(x + 12, y - 12, label)

    # top findings
    y -= 0.65 * inch
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(GOLD)
    c.drawString(margin, y, "TOP FINDINGS")
    y -= 0.22 * inch
    sev_rank = {"BLOCKER": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "FYI": 4}
    top = sorted(record.get("flags", []), key=lambda f: sev_rank.get(f.get("severity"), 9))[:4]
    for f in top:
        sev = f.get("severity", "")
        c.setFillColor(SEV_COLORS.get(sev, FAINT))
        c.setFont("Helvetica-Bold", 8)
        c.drawString(margin, y, sev)
        c.setFillColor(CREAM)
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(margin + 62, y, (f.get("category", "").replace("_", " ").title())[:40])
        c.setFillColor(colors.HexColor("#9aa3b2"))
        c.setFont("Helvetica", 8)
        finding = (f.get("finding") or "")[:150].replace("\n", " ")
        c.drawString(margin + 62, y - 11, finding[:110])
        c.drawString(margin + 62, y - 21, finding[110:150])
        rc = (f.get("remedy") or {}).get("est_cost_usd")
        if rc and len(rc) == 2 and rc[0] >= 0:
            c.setFont("Helvetica-Bold", 9)
            c.setFillColor(CREAM)
            label = "no fee expected" if rc == [0, 0] else f"${rc[0]:,.0f}–${rc[1]:,.0f}"
            c.drawRightString(w - margin, y, label)
        y -= 0.52 * inch

    # rating strip
    pred = rep.get("rating_prediction") or {}
    if pred.get("predicted"):
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(GOLD)
        c.drawString(margin, y, "RATING")
        comps = pred.get("comparables") or []
        same = sum(1 for x in comps if x.get("rating") == pred["predicted"])
        c.setFillColor(CREAM)
        c.setFont("Helvetica-Bold", 11)
        line = f"Predicted {pred['predicted']}"
        if pred.get("target") and pred["target"] != pred["predicted"]:
            line += f" · production target {pred['target']}"
        order = ["G", "PG", "PG-13", "R", "NC-17"]
        predicted = pred["predicted"]
        pred_i = order.index(predicted) if predicted in order else -1
        at_or_above = (
            sum(
                1
                for comp in comps
                if comp.get("rating") in order and order.index(comp["rating"]) >= pred_i
            )
            if pred_i >= 0
            else same
        )
        line += (
            f" — {at_or_above} of {len(comps)} nearest released comparables "
            f"rate {predicted} or stricter"
        )
        c.drawString(margin + 62, y, line[:95])
        y -= 0.35 * inch

    c.setFont("Helvetica", 7)
    c.setFillColor(FAINT)
    when = (record.get("generated_at") or "")[:10]
    c.drawString(
        margin,
        0.55 * inch,
        f"scriptrisk.com · generated {when} · every finding cited and independently verified · "
        "research tool, not legal advice",
    )
    c.showPage()
    c.save()
    return buf.getvalue()

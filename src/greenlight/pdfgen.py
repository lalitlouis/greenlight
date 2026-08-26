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
    story.append(
        Paragraph(
            f"Generated {data['generated_at']} · Greenlight Score {data.get('score', '—')}/100 · "
            f"{counts.get('BLOCKER', 0)} blocker(s), {counts.get('HIGH', 0)} high, "
            f"{counts.get('MEDIUM', 0)} medium · prepared by ScriptRisk (scriptrisk.com)",
            sub_style,
        )
    )
    story.append(Spacer(1, 10))

    cols = data["columns"]
    widths = [0.75, 0.35, 1.35, 1.05, 0.95, 0.55, 1.15, 2.6, 0.7, 0.95, 0.45]
    total = sum(widths)
    page_w = landscape(letter)[0] - 0.9 * inch
    widths = [w / total * page_w for w in widths]

    rows: list[list[Any]] = [[Paragraph(c.upper(), _HEAD) for c in cols]]
    styles_extra = []
    for i, r in enumerate(data["rows"], start=1):
        style = _CELL_DIM if r.get("Clearance status") == "No known issue" else _CELL
        rows.append([Paragraph(str(r.get(c, "")), style) for c in cols])
        sev = r.get("Severity")
        if sev in SEV_COLORS:
            styles_extra.append(("TEXTCOLOR", (5, i), (5, i), SEV_COLORS[sev]))
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
    c.drawString(margin + 18, y, "SCRIPTRISK")
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
            c.drawRightString(w - margin, y, f"${rc[0]:,.0f}–${rc[1]:,.0f}")
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
        line += f" — {same} of {len(comps)} nearest released comparables agree"
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

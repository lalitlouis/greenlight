"""PDF intake adapter. A real PDF is generated with pdfplumber's sibling-free
route: we build a minimal one via fpdf-less raw construction is overkill — we
test the routing logic and extraction on a tiny hand-made PDF instead."""

from greenlight.pdf import looks_like_pdf, screenplay_text

MINI_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
    b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 82>>stream\n"
    b"BT /F1 12 Tf 72 720 Td (INT. NOWHERE - DAY) Tj 0 -24 Td (Something happens.) Tj ET\n"
    b"endstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


def test_fountain_bytes_pass_through():
    text = screenplay_text("script.fountain", b"INT. BAR - NIGHT\n\nHello.\n")
    assert text.startswith("INT. BAR - NIGHT")


def test_pdf_detection():
    assert looks_like_pdf(MINI_PDF)
    assert not looks_like_pdf(b"Title: X\n")


def test_pdf_extraction_yields_parseable_text():
    text = screenplay_text("script.pdf", MINI_PDF)
    assert "INT. NOWHERE - DAY" in text
    from greenlight.parser import parse_fountain

    _, scenes = parse_fountain(text)
    assert scenes and scenes[0]["int_ext"] == "INT"


def test_binder_pdf_escapes_title_markup():
    """reportlab Paragraph parses mini-XML — an unescaped '<' in a title raised
    ValueError and 500'd the download (review B17)."""
    from greenlight import pdfgen

    data = {
        "title": "A <B> & C's Movie",
        "generated_at": "2026-09-01",
        "score": None,
        "verification_degraded": True,
        "counts": {"HIGH": 1},
        "draft": {"sha256": "abc123def456ghi", "pages": 3, "scene_numbers": "generated"},
        "columns": ["Scene", "Item", "Severity", "Clearance status", "Finding"],
        "rows": [
            {
                "Scene": "S001",
                "Item": "Bar & <Grill>",
                "Severity": "HIGH",
                "Clearance status": (
                    "UNVERIFIED (verifier unavailable) — License / mitigation required"
                ),
                "Finding": "F100",
            }
        ],
        "est_cost": [100, 200],
        "est_cost_paths": {"as_written": [100, 200], "target_rating": [100, 150]},
        "back_matter": {"cleared": [{"desk": "Clearance Counsel", "text": "<ok> & fine"}]},
        "disclaimer": "Not legal advice <really> & truly.",
    }
    pdf = pdfgen.binder_pdf(data)
    assert pdf.startswith(b"%PDF")


def test_onesheet_pdf_renders_withheld_and_unverified_record():
    from greenlight import pdfgen

    record = {
        "script_title": "Slack <Tide> & Co",
        "generated_at": "2026-09-01",
        "flags": [
            {
                "flag_id": "F1",
                "severity": "BLOCKER",
                "category": "stunt_pyro",
                "finding": "[partially supported] Fire.",
                "remedy": {"est_cost_usd": [1, 2]},
                "verification_unavailable": True,
                "citations": [{"url": "https://x", "excerpt": "y"}],
            }
        ],
        "rejected_flags": [],
        "unexamined": [{"surface": "Ford", "scene_ids": ["S001"]}],
        "desks_incomplete": ["territory_censor"],
        "report": {
            "greenlight_score": None,
            "verification_degraded": True,
            "counts": {"BLOCKER": 1},
            "est_clearance_cost_usd": [1, 2],
            "est_cost_paths": {"as_written": [1, 2], "target_rating": [0, 1]},
            "rating_prediction": {
                "predicted": "R",
                "target": "PG-13",
                "comparables": [{"rating": "R"}],
            },
        },
    }
    pdf = pdfgen.onesheet_pdf(record)
    assert pdf.startswith(b"%PDF")

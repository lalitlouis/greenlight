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

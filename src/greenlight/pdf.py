"""PDF screenplay intake: extract text that the Fountain parser can read.

Screenplay PDFs (Final Draft, WriterDuet exports) keep the elements the parser
keys on — INT./EXT. sluglines and ALL-CAPS character cues survive plain text
extraction. This is deliberately a thin adapter: extraction happens here, and
everything downstream still speaks Fountain-shaped text through one parser.
"""

from __future__ import annotations

import io

MAX_PDF_PAGES = 400  # the longest shooting scripts are ~200pp; 400 is generous


def pdf_to_text(data: bytes) -> str:
    """Text from a PDF, page by page, line structure preserved. Page-capped:
    extraction cost scales with pages, and a crafted PDF should not own the CPU."""
    import pdfplumber  # heavyweight import, only when a PDF actually arrives

    lines: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages[:MAX_PDF_PAGES]:
            text = page.extract_text() or ""
            lines.append(text)
    return "\n\n".join(lines)


def looks_like_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def screenplay_text(filename: str, data: bytes) -> str:
    """Uploaded file -> parseable text. PDFs are extracted, FDX is converted
    with its native structure (locked scene numbers preserved); everything
    else is treated as Fountain/plain text."""
    if filename.lower().endswith(".pdf") or looks_like_pdf(data):
        return pdf_to_text(data)
    from greenlight.fdx import fdx_to_fountain, looks_like_fdx

    if looks_like_fdx(filename, data):
        return fdx_to_fountain(data)
    return data.decode("utf-8", errors="replace")

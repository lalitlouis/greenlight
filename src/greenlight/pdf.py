"""PDF screenplay intake: extract text that the Fountain parser can read.

Screenplay PDFs (Final Draft, WriterDuet exports) keep the elements the parser
keys on — INT./EXT. sluglines and ALL-CAPS character cues survive plain text
extraction. This is deliberately a thin adapter: extraction happens here, and
everything downstream still speaks Fountain-shaped text through one parser.
"""

from __future__ import annotations

import io
import logging

MAX_PDF_PAGES = 400  # the longest shooting scripts are ~200pp; 400 is generous

_log = logging.getLogger(__name__)


def pdf_to_text(data: bytes, meta: dict | None = None) -> str:
    """Text from a PDF, page by page, line structure preserved. Page-capped:
    extraction cost scales with pages, and a crafted PDF should not own the CPU.

    The cap used to be silent (C12, 2026-09-01 review): pages past it vanished
    from the analysis with no trace. Now every truncation logs a structured
    warning (counts only — never script text) and, when the caller passes a
    `meta` dict, records `pages_total` / `pages_read` / `pages_truncated` in it
    so the run can disclose what was not read."""
    import pdfplumber  # heavyweight import, only when a PDF actually arrives

    lines: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        total = len(pdf.pages)
        for page in pdf.pages[:MAX_PDF_PAGES]:
            text = page.extract_text() or ""
            lines.append(text)
    truncated = max(0, total - MAX_PDF_PAGES)
    if meta is not None:
        meta["pages_total"] = total
        meta["pages_read"] = min(total, MAX_PDF_PAGES)
        meta["pages_truncated"] = truncated
    if truncated:
        _log.warning(
            "pdf_truncated pages_total=%d pages_read=%d pages_truncated=%d",
            total,
            MAX_PDF_PAGES,
            truncated,
        )
    # Form feed between pages: the parser anchors scenes to the PDF's REAL
    # pages instead of the ~55-line estimate (which drifted 17 pages by act
    # three on a 111-page script — a line producer flips to the wrong page).
    return "\n\f\n".join(lines)


def looks_like_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def screenplay_text(filename: str, data: bytes, meta: dict | None = None) -> str:
    """Uploaded file -> parseable text. PDFs are extracted, FDX is converted
    with its native structure (locked scene numbers preserved); everything
    else is treated as Fountain/plain text. `meta`, when given, receives the
    PDF page accounting (see pdf_to_text) so a page-cap truncation is visible."""
    if filename.lower().endswith(".pdf") or looks_like_pdf(data):
        return pdf_to_text(data, meta)
    from greenlight.fdx import fdx_to_fountain, looks_like_fdx

    if looks_like_fdx(filename, data):
        return fdx_to_fountain(data)
    return data.decode("utf-8", errors="replace")

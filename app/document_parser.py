from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from app.config import settings


def extract_pdf_text(pdf_bytes: bytes) -> str:
    if not pdf_bytes:
        return ""

    reader = PdfReader(BytesIO(pdf_bytes))
    chunks: list[str] = []
    for index, page in enumerate(reader.pages):
        if index >= settings.notice_pdf_page_limit:
            break
        page_text = page.extract_text() or ""
        if page_text.strip():
            chunks.append(page_text)

    merged = "\n".join(chunks).strip()
    if not merged:
        return ""
    return merged[: settings.notice_text_char_limit]

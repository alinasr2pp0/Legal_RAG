"""Local text extraction for uploaded case documents.

Supported: .txt/.md, .docx, and PDFs with an embedded text layer.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

TEXT_EXT = {".txt", ".md"}
SUPPORTED_EXT = TEXT_EXT | {".docx", ".pdf"}


class ExtractionError(Exception):
    """User-facing extraction problem (message is Arabic, safe to show)."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Page:
    number: int
    text: str


@dataclass
class Extracted:
    pages: list[Page] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text)


def _clean(text: str) -> str:
    text = text.replace("\x00", "").replace("‏", "").replace("‎", "")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _from_pdf(data: bytes) -> Extracted:
    import pymupdf

    try:
        doc: Any = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError("تعذّرت قراءة ملف PDF (تالف أو محمي بكلمة مرور).") from exc
    out = Extracted()
    with doc:
        for i, page in enumerate(doc, start=1):
            text = _clean(page.get_text("text"))
            if text:
                out.pages.append(Page(i, text))
    return out


def _from_docx(data: bytes) -> Extracted:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = ElementTree.fromstring(z.read("word/document.xml"))  # noqa: S314
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ExtractionError("ملف Word غير صالح.") from exc
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paras = []
    for p in root.iter(ns + "p"):
        text = "".join(t.text or "" for t in p.iter(ns + "t"))
        if text.strip():
            paras.append(text)
    return Extracted([Page(1, _clean("\n".join(paras)))])


def extract(filename: str, data: bytes) -> Extracted:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXT:
        raise ExtractionError(
            "نوع الملف غير مدعوم. المدعوم: PDF ذو طبقة نصية، Word (docx)، وملفات النص."
        )
    if ext in TEXT_EXT:
        text = data.decode("utf-8", errors="ignore") or data.decode("cp1256", errors="ignore")
        result = Extracted([Page(1, _clean(text))])
    elif ext == ".docx":
        result = _from_docx(data)
    elif ext == ".pdf":
        result = _from_pdf(data)
    if not result.text.strip():
        raise ExtractionError("لم يُستخرج أي نص من الملف.")
    return result

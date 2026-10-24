"""In-memory store for user-uploaded case documents.

Isolation by design: case text lives only in process memory (gone on restart or
after ``case_ttl_hours``), is indexed with its own BM25 index, and is never
written to the Civil Code vector index, the query log or the eval data.
"""

from __future__ import annotations

import math
import re
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field

from core.config import settings
from core.guardrails import detect_injection
from core.models import Chunk, ScoredChunk
from rag.ingestion.case_extract import Extracted
from rag.query_processing.query_analysis import bm25_tokens

_CHUNK_CHARS = 700
_OVERLAP = 120


class CaseError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class CaseDoc:
    doc_id: str
    filename: str
    chars: int
    pages: int
    chunks: list[Chunk]
    skipped_injection: int = 0


@dataclass
class Case:
    case_id: str
    name: str
    created: float = field(default_factory=time.time)
    touched: float = field(default_factory=time.time)
    docs: dict[str, CaseDoc] = field(default_factory=dict)
    _all: list[Chunk] = field(default_factory=list)
    _tf: list[Counter[str]] = field(default_factory=list)
    _df: Counter[str] = field(default_factory=Counter)

    def rebuild(self) -> None:
        self._all = [c for d in self.docs.values() for c in d.chunks]
        self._tf = [Counter(bm25_tokens(c.text)) for c in self._all]
        self._df = Counter(t for tf in self._tf for t in tf)

    def score(self, tokens: list[str]) -> list[float]:
        """BM25 with a smoothed IDF (rank_bm25's goes negative on tiny corpora like a case)."""
        n = len(self._all)
        avg = (sum(sum(tf.values()) for tf in self._tf) / n) or 1.0
        out = []
        for tf in self._tf:
            length = sum(tf.values())
            total = 0.0
            for t in set(tokens):
                f = tf.get(t, 0)
                if not f:
                    continue
                idf = math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5))
                total += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * length / avg))
            out.append(total)
        return out


def split_text(text: str) -> list[str]:
    """Paragraph-aware windows of ~700 chars with a small overlap."""
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    out: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 <= _CHUNK_CHARS:
            buf = f"{buf} {p}".strip()
            continue
        if buf:
            out.append(buf)
        while len(p) > _CHUNK_CHARS:
            out.append(p[:_CHUNK_CHARS])
            p = p[_CHUNK_CHARS - _OVERLAP:]
        buf = p
    if buf:
        out.append(buf)
    return out


class CaseStore:
    def __init__(self) -> None:
        self._cases: dict[str, Case] = {}
        self._lock = threading.Lock()

    def _evict(self) -> None:
        cutoff = time.time() - settings.case_ttl_hours * 3600
        for cid in [k for k, c in self._cases.items() if c.touched < cutoff]:
            del self._cases[cid]

    def create(self, name: str) -> Case:
        with self._lock:
            self._evict()
            case = Case(uuid.uuid4().hex[:12], name.strip()[:80] or "قضية جديدة")
            self._cases[case.case_id] = case
            return case

    def get(self, case_id: str) -> Case:
        with self._lock:
            self._evict()
            case = self._cases.get(case_id)
            if case is None:
                raise CaseError("القضية غير موجودة أو انتهت صلاحيتها. أنشئ قضية جديدة.", 404)
            case.touched = time.time()
            return case

    def delete(self, case_id: str) -> None:
        with self._lock:
            self._cases.pop(case_id, None)

    def add_document(self, case_id: str, filename: str, extracted: Extracted) -> CaseDoc:
        case = self.get(case_id)
        with self._lock:
            if len(case.docs) >= settings.case_max_docs:
                raise CaseError(f"الحد الأقصى {settings.case_max_docs} مستندات لكل قضية.", 413)
            total = sum(d.chars for d in case.docs.values()) + len(extracted.text)
            if total > settings.case_max_chars:
                raise CaseError("تجاوزت الحد الأقصى لحجم نصوص القضية.", 413)
            doc_id = uuid.uuid4().hex[:8]
            chunks: list[Chunk] = []
            skipped = 0
            for page in extracted.pages:
                lines = page.text.split("\n")
                if settings.injection_guard_enabled:
                    # lines that try to instruct the model are dropped before chunking
                    kept = [ln for ln in lines if not detect_injection(ln)]
                    skipped += len(lines) - len(kept)
                    lines = kept
                for part in split_text("\n".join(lines)):
                    chunks.append(Chunk(
                        chunk_id=f"case:{case_id}:{doc_id}:{len(chunks)}",
                        text=part,
                        article_ids=[],
                        metadata={"source": "case", "doc": filename, "page": page.number},
                    ))
            if not chunks:
                raise CaseError("لم يتبقَّ نص صالح للاستخدام في هذا الملف.")
            doc = CaseDoc(
                doc_id, filename[:120], len(extracted.text), len(extracted.pages), chunks, skipped
            )
            case.docs[doc_id] = doc
            case.rebuild()
            return doc

    def remove_document(self, case_id: str, doc_id: str) -> None:
        case = self.get(case_id)
        with self._lock:
            case.docs.pop(doc_id, None)
            case.rebuild()

    def search(self, case_id: str, query: str, top_k: int | None = None) -> list[ScoredChunk]:
        case = self.get(case_id)
        k = top_k or settings.case_top_k
        chunks = case._all  # noqa: SLF001
        if not chunks:
            return []
        scores = case.score(bm25_tokens(query))
        ranked = [i for i in sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
                  if scores[i] > 0]
        if not ranked:  # generic question ("لخّص القضية"): fall back to the opening excerpts
            return [ScoredChunk(chunk=c, score=0.0) for c in chunks[:k]]
        return [ScoredChunk(chunk=chunks[i], score=float(scores[i])) for i in ranked]


case_store = CaseStore()

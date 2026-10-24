"""Orchestrator: owns the control flow of one question.

    guardrail (PII) -> retriever agent -> writer agent -> critic agent
                                             ^______ feedback ______|  (<= N revisions)

It returns a typed result including the critic's verdict so the API can
expose it and Prometheus can count it.
"""

from __future__ import annotations

import time
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from typing import Any, Protocol

from agents.retriever import Evidence, RetrieverAgent
from agents.writer import Draft, WriterAgent
from core.config import settings
from core.guardrails import redact_pii
from core.models import Citation, ScoredChunk
from rag.validation.critic import CriticAgent, Verdict

NO_EVIDENCE_ANSWER = (
    "لم أجد في نصوص القانون المدني المصري المتاحة ما يكفي للإجابة عن هذا السؤال. "
    "يُرجى إعادة صياغته أو ذكر رقم المادة المقصودة."
)
TEXT_UNAVAILABLE_ANSWER = (
    "نص المادة المطلوبة غير متوفر في المصدر المتاح للنظام، لذا لا يمكنني الإجابة عنها دون "
    "تخمين. يُرجى الرجوع إلى النص الرسمي للقانون."
)
UNVERIFIED_NOTE = ""
INCOMPLETE_NOTE = (
    "\n\n⚠️ ملاحظة: نص المادة {n} في المصدر ناقص (الفقرة (1) بالعربية غير متوفرة)، "
    "فلا تعتمد على هذه الإجابة دون مراجعة النص الرسمي."
)
SAFE_FALLBACK_HEAD = (
    "تعذّر التحقق من صحة الإجابة المولّدة (إشارة إلى مواد غير موجودة في النصوص المسترجعة)، "
    "فهذه هي النصوص ذات الصلة كما وردت دون تلخيص:\n"
)
EMPTY_QUESTION_ANSWER = "يُرجى كتابة سؤال قانوني متعلق بالقانون المدني المصري."


class SpanFactory(Protocol):
    def span(self, name: str, **kwargs: Any) -> AbstractContextManager[Any]: ...


@dataclass
class OrchestratorResult:
    question: str  # the (PII-redacted) question actually processed
    answer: str
    citations: list[Citation]
    verdict: Verdict | None
    revisions: int = 0
    used_web: bool = False
    pii_found: list[str] = field(default_factory=list)
    article_numbers: list[int] = field(default_factory=list)
    latency_ms: float = 0.0
    contexts: list[str] = field(default_factory=list)
    evidence_chunks: list[ScoredChunk] = field(default_factory=list)  # added for debug diagnostics
    question: str  # the (PII-redacted) question actually processed
    answer: str
    citations: list[Citation]
    verdict: Verdict | None
    revisions: int = 0
    used_web: bool = False
    pii_found: list[str] = field(default_factory=list)
    article_numbers: list[int] = field(default_factory=list)
    latency_ms: float = 0.0
    contexts: list[str] = field(default_factory=list)


class Orchestrator:
    def __init__(
        self,
        retriever: RetrieverAgent,
        writer: WriterAgent,
        critic: CriticAgent,
        max_revisions: int | None = None,
    ) -> None:
        self.retriever = retriever
        self.writer = writer
        self.critic = critic
        self.max_revisions = (
            settings.agent_max_revisions if max_revisions is None else max_revisions
        )

    def run(
        self,
        question: str,
        spans: SpanFactory | None = None,
        extra_chunks: list[ScoredChunk] | None = None,
    ) -> OrchestratorResult:
        """``extra_chunks``: user case excerpts, passed to the writer as facts only
        (they carry no article number, so they can never become citations)."""
        start = time.perf_counter()

        def span(name: str, **kw: Any) -> AbstractContextManager[Any]:
            return spans.span(name, **kw) if spans is not None else nullcontext()

        pii = redact_pii(question) if settings.pii_redaction_enabled else None
        safe_question = pii.text if pii else question
        pii_found = pii.found if pii else []

        if not safe_question.strip():
            return OrchestratorResult(
                safe_question, EMPTY_QUESTION_ANSWER, [], None, pii_found=pii_found
            )

        with span("retrieve", input=safe_question):
            evidence: Evidence = self.retriever.run(safe_question)
            if extra_chunks:
                evidence.chunks.extend(extra_chunks)

        # Articles whose text is absent from the source must never be "answered" from thin air.
        missing = [c for c in evidence.chunks if c.chunk.metadata.get("text_missing")]
        if missing:
            evidence.chunks = [
                c for c in evidence.chunks if not c.chunk.metadata.get("text_missing")
            ]
            if not evidence.chunks:
                return self._finish(
                    OrchestratorResult(
                        safe_question, TEXT_UNAVAILABLE_ANSWER, [], None,
                        pii_found=pii_found,
                        article_numbers=evidence.analysis.article_numbers,
                    ),
                    start,
                )

        if evidence.empty:
            return self._finish(
                OrchestratorResult(
                    safe_question, NO_EVIDENCE_ANSWER, [], None,
                    pii_found=pii_found,
                    article_numbers=evidence.analysis.article_numbers,
                ),
                start,
            )

        feedback: str | None = None
        revisions = 0
        draft: Draft
        verdict: Verdict
        while True:
            with span("write", input=feedback or ""):
                draft = self.writer.run(safe_question, evidence, feedback)
            with span("critic"):
                verdict = self.critic.run(draft, evidence)
            if verdict.passed or revisions >= self.max_revisions:
                break
            feedback = verdict.feedback
            revisions += 1

        answer, citations = draft.answer, draft.citations
        if not verdict.passed:
            # Fail safe: never hand back an unverified answer as if it were verified.
            if "phantom_citation" in verdict.issues:
                answer, citations = self._safe_fallback(evidence)
            else:
                answer = UNVERIFIED_NOTE + answer
        cited_nums = {c.article_number for c in citations}
        for c in evidence.chunks:
            n = c.chunk.metadata.get("number")
            if c.chunk.metadata.get("text_incomplete") and n in cited_nums:
                answer += INCOMPLETE_NOTE.format(n=n)
                break

        return self._finish(
            OrchestratorResult(
                question=safe_question,
                answer=answer,
                citations=citations,
                verdict=verdict,
                revisions=revisions,
                used_web=evidence.used_web,
                pii_found=pii_found,
                article_numbers=evidence.analysis.article_numbers,
                contexts=draft.contexts,
                evidence_chunks=evidence.chunks,
            ),
            start,
        )

    @staticmethod
    def _safe_fallback(evidence: Evidence) -> tuple[str, list[Citation]]:
        """Deterministic extractive answer: the retrieved article texts, verbatim."""
        parts: list[str] = []
        cites: list[Citation] = []
        for c in evidence.article_chunks[:3]:
            n = int(str(c.chunk.metadata["number"]))
            excerpt = c.chunk.text.strip()[:600]
            parts.append(f"المادة {n}: {excerpt}")
            cites.append(
                Citation(article_id=f"article_{n}", article_number=n, snippet=excerpt[:200])
            )
        if not parts:
            return NO_EVIDENCE_ANSWER, []
        return SAFE_FALLBACK_HEAD + "\n\n".join(parts), cites

    @staticmethod
    def _finish(result: OrchestratorResult, start: float) -> OrchestratorResult:
        result.latency_ms = (time.perf_counter() - start) * 1000
        return result

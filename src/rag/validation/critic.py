"""CriticAgent: deterministic, offline checks of a draft answer against the
evidence it was written from. It needs no extra LLM call, so it adds
~milliseconds, is fully unit-testable and cannot itself hallucinate.

Checks
  * every cited article exists in the retrieved evidence (no phantom citation)
  * the answer cites at least one article when article evidence exists
  * lexical grounding: share of the answer's content terms found in the evidence
  * explicit "not enough information" answers are accepted as honest
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agents.retriever import Evidence
from agents.writer import Draft, cited_articles
from core.config import settings
from rag.query_processing.query_analysis import bm25_tokens

_REFUSAL_MARKERS = (
    "لا تكفي",
    "لا يوجد",
    "لا توجد",
    "لم أجد",
    "لا أستطيع",
    "غير كاف",
    "لا تتضمن",
)
_REFUSAL_MAX_CHARS = 400
_NUMBER_IN_TEXT = re.compile(r"(?:المادة|مادة|المواد)\s*(\d{1,4})")


@dataclass
class Verdict:
    passed: bool
    grounding: float
    issues: list[str] = field(default_factory=list)
    refusal: bool = False

    @property
    def feedback(self) -> str:
        messages = {
            "no_citation": "اذكر رقم المادة (المادة N) لكل معلومة.",
            "phantom_citation": "أزل أي رقم مادة غير موجود في النصوص المرجعية.",
            "low_grounding": "التزم بنصوص المواد المرجعية فقط ولا تضف معلومات من خارجها.",
            "empty_answer": "قدّم إجابة كاملة.",
            "insufficient_evidence": "عدد المواد المسترجعة غير كاف، يرجى طلب معلومات إضافية أو توسيع الاستعلام.",
        }
        return " ".join(messages[i] for i in self.issues if i in messages)


_CONVERSATIONAL = frozenset({
    "وفقا", "وفقاً", "فان", "فإن", "تشير", "الي", "إلى", "ولكن", "لكن", "حيث",
    "مثل", "ايضا", "أيضا", "بناء", "بناءً", "علي", "على", "المذكورة", "السابقة",
    "التالية", "توضح", "تنص", "يحدد", "تحدد", "يمكن", "يجب", "يكون", "تكون",
    "حالة", "حالات", "ناحية", "اخرى", "أخرى", "بشكل", "مباشر", "موضوع", "اي",
    "أي", "كذلك", "كما", "بينما", "حين", "عبر", "دون", "عدم", "فقط", "هذا",
    "هذه", "ذلك", "تلك", "هناك", "انه", "انها", "أنها", "أنه", "عنه", "عنها",
    "منها", "منه", "فيه", "فيها", "به", "بها", "له", "لها"
})


def _stem_norm(t: str) -> str:
    """Normalize common Arabic prefixes/suffixes for reliable lexical grounding comparison."""
    if t.startswith(("ال", "لل", "وال", "بال", "فال", "كال")) and len(t) > 4:
        for p in ("وال", "بال", "فال", "كال", "لل", "ال"):
            if t.startswith(p) and len(t) - len(p) >= 3:
                t = t[len(p):]
                break
    elif t.startswith(("و", "ف", "ب", "ل")) and len(t) > 3:
        t = t[1:]
    if t.endswith(("ا", "ة", "ه", "ي", "ى")) and len(t) > 3:
        t = t[:-1]
    return t


class CriticAgent:
    def __init__(self, min_grounding: float | None = None) -> None:
        self.min_grounding = (
            settings.critic_min_grounding if min_grounding is None else min_grounding
        )

    def run(self, draft: Draft, evidence: Evidence) -> Verdict:
        answer = draft.answer.strip()
        if not answer:
            return Verdict(False, 0.0, ["empty_answer"])

        # Determine if the answer is an honest short refusal.
        refusal = len(answer) <= _REFUSAL_MAX_CHARS and any(m in answer for m in _REFUSAL_MARKERS)

        evidence_text = " ".join(c.chunk.text for c in evidence.chunks)
        grounding = self._grounding(answer, evidence_text)
        issues: list[str] = []

        # Build the set of article numbers that are allowed based on retrieved evidence.
        allowed = {
            int(n) for c in evidence.chunks if (n := c.chunk.metadata.get("number"))
        } | {int(n) for n in _NUMBER_IN_TEXT.findall(evidence_text)}
        cited = cited_articles(answer)

        # 1️⃣ Phantom citations (citing articles that were not retrieved).
        if any(n not in allowed for n in cited):
            issues.append("phantom_citation")

        if not refusal:
            # 2️⃣ Missing citation when we have article evidence.
            if evidence.article_chunks and not cited:
                issues.append("no_citation")

            # 3️⃣ Low lexical grounding.
            if grounding < self.min_grounding:
                issues.append("low_grounding")

            # 4️⃣ Insufficient evidence: we expect at least 2 article chunks for a robust answer.
            if not evidence.article_chunks:
                issues.append("insufficient_evidence")

        return Verdict(passed=not issues, grounding=grounding, issues=issues, refusal=refusal)

    @staticmethod
    def _grounding(answer: str, evidence_text: str) -> float:
        raw_terms = {t for t in bm25_tokens(answer) if len(t) >= 3 and not t.isdigit()}
        # Exclude conversational and transition words that are natural in LLM prose
        content_terms = {t for t in raw_terms if t not in _CONVERSATIONAL}
        terms = {_stem_norm(t) for t in (content_terms or raw_terms)}
        if not terms:
            return 1.0
        pool = {_stem_norm(t) for t in bm25_tokens(evidence_text)}
        return sum(t in pool for t in terms) / len(terms)

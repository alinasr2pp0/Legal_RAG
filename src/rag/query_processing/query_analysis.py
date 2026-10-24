"""Query understanding on top of the project's ``legal_arabic_text`` module.

Produces everything the retriever agent needs from one pass over the raw
user question: normalized text, language, Egyptian-dialect flag, BM25 tokens,
the text to embed, and explicit article references ("المادة 163",
"Article 163") that allow direct lookup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag.ingestion import legal_arabic_text as lat

MAX_ARTICLE_NUMBER = 1149
_EN_ARTICLE = re.compile(r"\barticles?\s*(?:no\.?\s*)?(\d{1,4})\b", re.IGNORECASE)
_AR_RANGE = re.compile(r"(?:المواد|مواد)\s*(?:من\s*)?(\d{1,4})\s*(?:الى|الي|إلى|-|–)\s*(\d{1,4})")


def fold_lam_alef(token: str) -> str:
    """Lexical key that ignores the PDF's lam-alef ordering damage: "لا" and
    "ال" fold to the same key, so "ثلاث" (query) matches "ثالث" (damaged corpus)
    and the pipeline keeps working even for words no repair rule covers."""
    return token.replace("لا", "ال")


def bm25_tokens(text: str) -> list[str]:
    """Recommended BM25 tokens: legal_arabic_text tokenization + lam-alef fold."""
    return [fold_lam_alef(t) for t in lat.tokenize_for_bm25(text)]


@dataclass(frozen=True)
class QueryAnalysis:
    original: str
    normalized: str
    language: str
    egyptian_dialect: bool
    bm25_tokens: list[str]
    embedding_text: str
    article_numbers: list[int] = field(default_factory=list)

    @property
    def has_explicit_article(self) -> bool:
        return bool(self.article_numbers)


_AR_LIST = re.compile(
    r"(?:المادتين|المادتان|المواد|مواد)\s*(?:رقم\s*)?((?:\d{1,4}\s*[،,و]?\s*)+)"
)  # "المادتين 163 و164" / "المواد 1، 2، 3" (an enumeration, never a range)


def _valid(n: int) -> bool:
    return 1 <= n <= MAX_ARTICLE_NUMBER


def analyze_query(question: str) -> QueryAnalysis:
    profile = lat.legal_query_profile(question)
    normalized = str(profile["normalized_query"])

    numbers: list[int] = []
    refs = profile["legal_references"]
    for item in refs["articles"]:  # type: ignore[index]
        digits = re.sub(r"\D", "", item["article"])
        if digits:
            numbers.append(int(digits))
    numbers += [int(m) for m in _EN_ARTICLE.findall(normalized)]
    for lo, hi in _AR_RANGE.findall(normalized):
        a, b = int(lo), int(hi)
        if 0 < b - a <= 5:  # tiny ranges only; never fan out to hundreds
            numbers += list(range(a, b + 1))

    for group in _AR_LIST.findall(normalized):
        numbers += [int(d) for d in re.findall(r"\d{1,4}", group)][:5]

    ordered = list(dict.fromkeys(n for n in numbers if _valid(n)))

    return QueryAnalysis(
        original=question,
        normalized=normalized,
        language=str(profile["language"]),
        egyptian_dialect=bool(profile["egyptian_markers"]),
        bm25_tokens=bm25_tokens(question),
        embedding_text=lat.prepare_for_embedding(question),
        article_numbers=ordered,
    )

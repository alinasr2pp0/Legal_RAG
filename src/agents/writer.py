"""WriterAgent: turns evidence into an answer with article citations."""

from __future__ import annotations

import re
from dataclasses import dataclass

from agents.retriever import Evidence
from core.models import Citation
from rag.generation.llm_client import BaseLLMClient

_CITED = re.compile(
    r"(?:المادة|مادة|المواد|المادتين|article)\s*(?:رقم\s*)?\(?(\d{1,4})", re.IGNORECASE
)
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def cited_articles(answer: str) -> list[int]:
    """Article numbers the answer explicitly cites (order preserved)."""
    seen: list[int] = []
    for match in _CITED.finditer(answer.translate(_AR_DIGITS)):
        n = int(match.group(1))
        if n not in seen:
            seen.append(n)
    return seen


@dataclass
class Draft:
    answer: str
    citations: list[Citation]
    contexts: list[str]


class WriterAgent:
    def __init__(self, llm_client: BaseLLMClient) -> None:
        self.llm_client = llm_client

    def run(self, question: str, evidence: Evidence, feedback: str | None = None) -> Draft:
        result = self.llm_client.generate(question, evidence.chunks, feedback)
        cited = set(cited_articles(result.answer))
        # List only the articles the answer actually relies on; if the model
        # cited none (the critic will flag that) fall back to everything used.
        selected = [c for c in result.citations if c.article_number in cited] or result.citations
        return Draft(answer=result.answer, citations=selected, contexts=result.contexts)

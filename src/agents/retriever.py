"""RetrieverAgent: decides *where* to look (Civil Code index first, web as an
optional fallback) and returns the evidence the writer may use."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.config import settings
from core.models import ScoredChunk
from rag.query_processing.query_analysis import QueryAnalysis
from tools.search_documents import SearchDocumentsTool
from tools.tavily_search import TavilySearchTool


@dataclass
class Evidence:
    analysis: QueryAnalysis
    chunks: list[ScoredChunk]
    used_web: bool = False
    pinned_articles: list[int] = field(default_factory=list)

    @property
    def article_chunks(self) -> list[ScoredChunk]:
        return [c for c in self.chunks if c.chunk.metadata.get("number")]

    @property
    def empty(self) -> bool:
        return not self.chunks


class RetrieverAgent:
    def __init__(
        self,
        search_tool: SearchDocumentsTool,
        web_tool: TavilySearchTool | None = None,
        web_min_score: float | None = None,
    ) -> None:
        self.search_tool = search_tool
        self.web_tool = web_tool
        self.web_min_score = (
            settings.web_search_min_score if web_min_score is None else web_min_score
        )

    def run(self, question: str) -> Evidence:
        result = self.search_tool(question)
        evidence = Evidence(
            analysis=result.analysis,
            chunks=list(result.chunks),
            pinned_articles=result.pinned_articles,
        )
        if self._needs_web(result.top_score, bool(result.pinned_articles), evidence.empty):
            assert self.web_tool is not None
            web = self.web_tool(result.analysis.original, result.analysis.article_numbers)
            if web:
                evidence.chunks.extend(web)
                evidence.used_web = True
        return evidence

    def _needs_web(self, top_score: float, pinned: bool, empty: bool) -> bool:
        if self.web_tool is None or not self.web_tool.available or pinned:
            return False
        if empty:
            return True
        # Rerank scores are only comparable to the threshold when a real
        # reranker is active (RRF scores are ~0.03 and would always trip it).
        return settings.reranker_enabled and top_score < self.web_min_score

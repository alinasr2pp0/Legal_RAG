"""Tool: search the indexed Civil Code (hybrid retrieval + reranking)."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.models import ScoredChunk
from rag.query_processing.query_analysis import QueryAnalysis, analyze_query
from rag.reranking.reranker import BaseReranker
from rag.retrieval.hybrid import HybridRetriever


@dataclass
class SearchResult:
    analysis: QueryAnalysis
    chunks: list[ScoredChunk]
    candidates: int
    pinned_articles: list[int] = field(default_factory=list)

    @property
    def top_score(self) -> float:
        return self.chunks[0].score if self.chunks else float("-inf")


class SearchDocumentsTool:
    name = "search_documents"
    description = "Hybrid (dense+BM25) search over Egyptian Civil Code articles, then rerank."

    def __init__(
        self,
        retriever: HybridRetriever,
        reranker: BaseReranker,
        top_k_retrieval: int,
        top_k_rerank: int,
    ) -> None:
        self.retriever = retriever
        self.reranker = reranker
        self.top_k_retrieval = top_k_retrieval
        self.top_k_rerank = top_k_rerank

    def __call__(self, question: str) -> SearchResult:
        analysis = analyze_query(question)
        candidates = self.retriever.retrieve_analyzed(analysis, self.top_k_retrieval)
        reranked = self.reranker.rerank(
            analysis.normalized or question, candidates, self.top_k_rerank
        )
        # The reranker must not demote an article the user asked for by number.
        pinned = self.retriever.bm25_index.lookup_articles(analysis.article_numbers)
        final = self.retriever.pin(pinned, reranked, self.top_k_rerank)
        return SearchResult(
            analysis=analysis,
            chunks=final,
            candidates=len(candidates),
            pinned_articles=analysis.article_numbers,
        )

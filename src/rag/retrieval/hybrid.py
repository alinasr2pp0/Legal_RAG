"""Hybrid retrieval: dense + sparse candidates, fused with RRF, explicit articles pinned."""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.models import ScoredChunk
from rag.embedding.embedder import BaseEmbedder
from rag.fusion.rrf import RRF_K, reciprocal_rank_fusion
from rag.indexing.vector_store import BaseVectorStore
from rag.query_processing.query_analysis import QueryAnalysis, analyze_query
from rag.retrieval.dense import DenseRetriever
from rag.retrieval.sparse import BM25Index


class BaseRetriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, top_k: int) -> list[ScoredChunk]: ...


class HybridRetriever(BaseRetriever):
    def __init__(
        self,
        embedder: BaseEmbedder,
        vector_store: BaseVectorStore,
        bm25_index: BM25Index,
        rrf_k: int = RRF_K,
    ) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self.bm25_index = bm25_index
        self.dense = DenseRetriever(embedder, vector_store)
        self.rrf_k = rrf_k

    def retrieve(self, query: str, top_k: int) -> list[ScoredChunk]:
        return self.retrieve_analyzed(analyze_query(query), top_k)

    def retrieve_analyzed(self, analysis: QueryAnalysis, top_k: int) -> list[ScoredChunk]:
        dense_results = self.dense.search(analysis.embedding_text, top_k * 2)
        sparse_results = self.bm25_index.search(analysis.bm25_tokens, top_k=top_k * 2)
        fused = self._fuse(dense_results, sparse_results, top_k)
        pinned = self.bm25_index.lookup_articles(analysis.article_numbers)
        return self.pin(pinned, fused, top_k)

    @staticmethod
    def pin(pinned: list[ScoredChunk], rest: list[ScoredChunk], top_k: int) -> list[ScoredChunk]:
        """Explicitly requested articles always come first (deduplicated)."""
        out: list[ScoredChunk] = []
        seen: set[str] = set()
        for item in [*pinned, *rest]:
            if item.chunk.chunk_id not in seen:
                seen.add(item.chunk.chunk_id)
                out.append(item)
        return out[: max(top_k, len(pinned))]

    def _fuse(
        self, dense: list[ScoredChunk], sparse: list[ScoredChunk], top_k: int
    ) -> list[ScoredChunk]:
        return reciprocal_rank_fusion([dense, sparse], top_k, self.rrf_k)

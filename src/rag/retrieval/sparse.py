"""Sparse retrieval: BM25 over the chunk corpus (Arabic legal tokenizer)."""

from __future__ import annotations

from rank_bm25 import BM25Okapi

from core.models import Chunk, ScoredChunk
from rag.query_processing.query_analysis import bm25_tokens


class BM25Index:
    """In-memory sparse index built once from the full chunk corpus."""

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.bm25 = BM25Okapi([bm25_tokens(c.text) or ["_"] for c in chunks])
        self.by_number: dict[int, list[Chunk]] = {}
        for c in chunks:
            number = c.metadata.get("number")
            if isinstance(number, int):
                self.by_number.setdefault(number, []).append(c)

    def lookup_articles(self, numbers: list[int]) -> list[ScoredChunk]:
        """Exact lookup by article number (all chunks of each article)."""
        return [
            ScoredChunk(chunk=c, score=1.0)
            for n in numbers
            for c in self.by_number.get(n, [])
        ]

    def search(self, query: str | list[str], top_k: int) -> list[ScoredChunk]:
        tokens = bm25_tokens(query) if isinstance(query, str) else query
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [ScoredChunk(chunk=self.chunks[i], score=float(scores[i])) for i in ranked]

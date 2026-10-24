"""Tests HybridRetriever's RRF fusion logic with a fake vector store and
BM25 index — no real embedding/vector-store calls, pure algorithm verification."""
from unittest.mock import MagicMock

from core.models import Chunk, ScoredChunk
from rag.retrieval.hybrid import HybridRetriever


def _chunk(cid: str) -> Chunk:
    return Chunk(chunk_id=cid, text=f"text {cid}", article_ids=[cid])


def test_fusion_prioritizes_items_ranked_high_in_both_lists():
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1, 0.2, 0.3]

    vector_store = MagicMock()
    vector_store.query.return_value = [
        ScoredChunk(chunk=_chunk("a"), score=0.9),
        ScoredChunk(chunk=_chunk("b"), score=0.8),
        ScoredChunk(chunk=_chunk("c"), score=0.7),
    ]

    bm25_index = MagicMock()
    bm25_index.lookup_articles.return_value = []
    bm25_index.search.return_value = [
        ScoredChunk(chunk=_chunk("b"), score=5.0),
        ScoredChunk(chunk=_chunk("a"), score=4.0),
        ScoredChunk(chunk=_chunk("d"), score=3.0),
    ]

    retriever = HybridRetriever(embedder, vector_store, bm25_index)
    results = retriever.retrieve("query", top_k=4)

    result_ids = [r.chunk.chunk_id for r in results]
    # 'a' and 'b' appear near the top of BOTH lists -> must outrank 'c'/'d'
    # which appear in only one list.
    assert result_ids.index("a") < result_ids.index("c")
    assert result_ids.index("b") < result_ids.index("d")
    embedder.embed_query.assert_called_once()


def test_fusion_handles_empty_bm25_results():
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1]
    vector_store = MagicMock()
    vector_store.query.return_value = [ScoredChunk(chunk=_chunk("a"), score=0.9)]
    bm25_index = MagicMock()
    bm25_index.lookup_articles.return_value = []
    bm25_index.search.return_value = []

    retriever = HybridRetriever(embedder, vector_store, bm25_index)
    results = retriever.retrieve("query", top_k=5)
    assert len(results) == 1
    assert results[0].chunk.chunk_id == "a"

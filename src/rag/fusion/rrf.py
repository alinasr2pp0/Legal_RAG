"""Reciprocal Rank Fusion: score(d) = sum over rankings of 1 / (k + rank(d))."""

from __future__ import annotations

from core.models import Chunk, ScoredChunk

RRF_K = 60


def reciprocal_rank_fusion(
    rankings: list[list[ScoredChunk]], top_k: int, k: int = RRF_K
) -> list[ScoredChunk]:
    if top_k <= 0:
        return []
    scores: dict[str, float] = {}
    chunks: dict[str, Chunk] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            cid = item.chunk.chunk_id
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            chunks[cid] = item.chunk
    ranked_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:top_k]
    return [ScoredChunk(chunk=chunks[cid], score=scores[cid]) for cid in ranked_ids]

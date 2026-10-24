from core.models import Chunk, ScoredChunk
from rag.fusion.rrf import reciprocal_rank_fusion


def _scored(chunk_id: str, score: float) -> ScoredChunk:
    return ScoredChunk(
        chunk=Chunk(chunk_id=chunk_id, text=chunk_id, article_ids=[chunk_id]), score=score
    )


def test_rrf_rewards_shared_high_rank_results():
    dense = [_scored("shared", 0.9), _scored("dense-only", 0.8)]
    sparse = [_scored("shared", 4.0), _scored("sparse-only", 3.0)]
    result = reciprocal_rank_fusion([dense, sparse], top_k=3)
    assert [r.chunk.chunk_id for r in result] == ["shared", "dense-only", "sparse-only"]
    assert result[0].score > result[1].score


def test_rrf_handles_empty_lists_and_nonpositive_limit():
    assert reciprocal_rank_fusion([[], []], top_k=3) == []
    assert reciprocal_rank_fusion([[_scored("a", 1.0)]], top_k=0) == []
    assert reciprocal_rank_fusion([[_scored("a", 1.0)]], top_k=-1) == []

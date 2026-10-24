"""Unit tests for the separated RAG stages: fusion, context building, prompts."""
from core.models import Chunk, ScoredChunk
from rag.context_building.builder import build_context_block, build_user_prompt, label
from rag.fusion.rrf import RRF_K, reciprocal_rank_fusion
from rag.generation.prompts import system_prompt


def _c(cid: str, **meta) -> ScoredChunk:
    return ScoredChunk(chunk=Chunk(chunk_id=cid, text=f"text {cid}", article_ids=[cid],
                                   metadata=meta), score=1.0)


def test_rrf_rewards_agreement_between_rankings():
    a, b, c = _c("a"), _c("b"), _c("c")
    out = reciprocal_rank_fusion([[a, b], [c, b]], top_k=3)
    assert out[0].chunk.chunk_id == "b"  # ranked by both lists
    assert abs(out[0].score - (1 / (RRF_K + 2) + 1 / (RRF_K + 2))) < 1e-9
    assert len(reciprocal_rank_fusion([[a, b], [c, b]], top_k=2)) == 2


def test_context_labels_articles_repealed_case_and_web():
    assert label(_c("x", number=163)) == "مادة 163"
    assert label(_c("x", number=54, is_repealed=True)).endswith("ملغاة")
    assert label(_c("x", source="case", doc="d.pdf", page=2)).startswith("مستند القضية")
    assert "ويب" in label(_c("x"))
    block = build_context_block([_c("a", number=1), _c("b", number=2)])
    assert block.index("[مادة 1]") < block.index("[مادة 2]")
    assert "ملاحظات المراجع" in build_user_prompt("س", [_c("a", number=1)], "صحّح")


def test_case_prompt_only_added_when_case_evidence_present():
    assert "مستند القضية" not in system_prompt([_c("a", number=1)])
    assert "مستند القضية" in system_prompt([_c("a", source="case")])

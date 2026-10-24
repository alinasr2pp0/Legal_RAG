"""End-to-end cache behaviour of /ask with a fake pipeline (no API keys)."""
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from api import main
from core.models import Chunk, Citation, RagAnswer, ScoredChunk
from rag.query_processing.query_analysis import analyze_query


def _install_fake_pipeline() -> MagicMock:
    chunk = Chunk(chunk_id="article_1_p0", text="نص", article_ids=["article_1"],
                  metadata={"number": 1})
    retriever = MagicMock()
    retriever.retrieve.return_value = [ScoredChunk(chunk=chunk, score=1.0)]
    reranker = MagicMock()
    reranker.rerank.return_value = [ScoredChunk(chunk=chunk, score=1.0)]
    llm = MagicMock()
    llm.generate.return_value = RagAnswer(
        question="q", answer="إجابة وفق المادة 1", contexts=["نص"],
        citations=[Citation(article_id="article_1", article_number=1, snippet="نص")],
    )
    from agents.orchestrator import Orchestrator
    from agents.retriever import RetrieverAgent
    from agents.writer import WriterAgent
    from rag.validation.critic import CriticAgent
    from tools.search_documents import SearchResult

    search_tool = MagicMock()
    search_tool.return_value = SearchResult(
        analysis=analyze_query("q"), chunks=[ScoredChunk(chunk=chunk, score=1.0)], candidates=1
    )
    orchestrator = Orchestrator(
        RetrieverAgent(search_tool, None), WriterAgent(llm), CriticAgent(min_grounding=0.0)
    )
    main._pipeline.clear()
    main._pipeline.update(
        retriever=retriever, reranker=reranker, llm_client=llm,
        search_tool=search_tool, orchestrator=orchestrator,
    )
    main._answer_cache.clear()
    return llm


def test_second_equivalent_question_is_served_from_cache():
    llm = _install_fake_pipeline()
    client = TestClient(main.app)

    r1 = client.post("/ask", json={"question": "ما هي شروط العقد؟"})
    r2 = client.post("/ask", json={"question": "ما هى شروط العقد"})
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json()
    assert llm.generate.call_count == 1

    stats = client.get("/cache/stats").json()["answer"]
    assert stats["hits"] == 1 and stats["misses"] == 1
    assert r1.json()["sources"][0]["citation"] == "Egyptian Civil Code, Article 1"

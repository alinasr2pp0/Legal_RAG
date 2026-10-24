"""End-to-end over the REAL committed corpus (data/serving/chunks.json) with an
embedded Qdrant, a deterministic hashing embedder and a fake LLM -- proves the
whole chain (tokenizer -> BM25 + dense -> RRF -> pin -> agents -> API) works
without any network or key."""
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agents.orchestrator import Orchestrator
from agents.retriever import RetrieverAgent
from agents.writer import WriterAgent
from api import main
from core.models import Chunk, Citation, RagAnswer, ScoredChunk
from rag.embedding.embedder import BaseEmbedder
from rag.indexing.vector_store import QdrantVectorStore
from rag.ingestion.legal_arabic_text import prepare_for_embedding
from rag.reranking.reranker import PassThroughReranker
from rag.retrieval.hybrid import HybridRetriever
from rag.retrieval.sparse import BM25Index
from rag.validation.critic import CriticAgent
from tools.search_documents import SearchDocumentsTool

CHUNKS = Path("data/serving/chunks.json")
DIM = 256

pytestmark = pytest.mark.skipif(not CHUNKS.exists(), reason="serving bundle not exported")


class HashEmbedder(BaseEmbedder):
    def _vec(self, text: str) -> list[float]:
        v = [0.0] * DIM
        for tok in prepare_for_embedding(text).split():
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class EchoLLM:
    def generate(self, question, contexts: list[ScoredChunk], feedback=None):
        top = contexts[0].chunk
        n = int(top.metadata["number"])
        return RagAnswer(
            question=question, answer=f"وفقا للمادة {n}: {top.text[:200]}",
            contexts=[c.chunk.text for c in contexts],
            citations=[Citation(article_id=c.chunk.article_ids[0],
                                article_number=int(c.chunk.metadata["number"]), snippet="")
                       for c in contexts if c.chunk.metadata.get("number")],
        )


@pytest.fixture(scope="module")
def orchestrator(tmp_path_factory) -> Orchestrator:
    chunks = [Chunk(**c) for c in json.loads(CHUNKS.read_text(encoding="utf-8"))]
    store = QdrantVectorStore(
        collection="e2e", dimension=DIM, path=str(tmp_path_factory.mktemp("qdrant"))
    )
    emb = HashEmbedder()
    store.upsert(chunks, emb.embed_documents([c.text for c in chunks]))
    retriever = HybridRetriever(emb, store, BM25Index(chunks))
    tool = SearchDocumentsTool(retriever, PassThroughReranker(), 20, 5)
    return Orchestrator(RetrieverAgent(tool, None), WriterAgent(EchoLLM()), CriticAgent())


def test_corpus_is_repaired_and_flags_are_boolean():
    chunks = json.loads(CHUNKS.read_text(encoding="utf-8"))
    assert len(chunks) >= 1100
    assert all(isinstance(c["metadata"]["is_repealed"], bool) for c in chunks)
    text = " ".join(c["text"] for c in chunks)
    assert "االلتزام" not in text and "اإليجار" not in text  # ligature damage repaired


def test_explicit_article_is_returned_first(orchestrator):
    result = orchestrator.run("ما نص المادة 163؟")
    assert result.citations[0].article_number == 163
    assert result.article_numbers == [163] and result.verdict.passed


def test_semantic_question_finds_the_right_article(orchestrator):
    result = orchestrator.run("ما حكم الإثراء بلا سبب على حساب شخص آخر؟")
    assert 179 in [c.article_number for c in result.citations]


def test_api_end_to_end_with_pii(orchestrator):
    main._pipeline.clear()
    main._pipeline.update(orchestrator=orchestrator)
    main._answer_cache.clear()
    client = TestClient(main.app)
    r = client.post("/ask", json={"question": "موبايلي 01012345678 ما نص المادة 164؟"})
    assert r.status_code == 200
    body = r.json()
    assert body["pii_redacted"] == ["phone"]
    assert body["sources"][0]["citation"] == "Egyptian Civil Code, Article 164"
    assert body["critic"]["passed"] is True
    main._pipeline.clear()


def test_stream_runs_full_pipeline_then_streams_verified_answer(orchestrator):
    main._pipeline.clear()
    main._pipeline.update(orchestrator=orchestrator)
    main._answer_cache.clear()
    client = TestClient(main.app)
    r = client.post("/ask/stream", json={"question": "ما نص المادة 164؟"})
    assert r.status_code == 200
    blocks = [b for b in r.text.split("\n\n") if b]
    assert blocks[0] == "event: status\ndata: searching"
    tokens = [b for b in blocks if not b.startswith("event:")]
    assert len(tokens) > 3  # streamed in chunks, not one blob
    result = json.loads(blocks[-1].split("data: ", 1)[1])
    assert blocks[-1].startswith("event: result")
    rebuilt = "".join(
        "\n".join(line[6:] for line in b.split("\n")) for b in tokens
    )
    assert rebuilt.strip() == result["answer"].strip()
    assert result["critic"]["passed"] is True and result["sources"][0]["article_number"] == 164
    main._pipeline.clear()


def test_stream_reports_pipeline_errors_as_event(monkeypatch):
    class FailingOrchestrator:
        def run(self, *args, **kwargs):
            raise RuntimeError("deliberate pipeline failure")

    monkeypatch.setattr(main, "_pipeline", {"orchestrator": FailingOrchestrator()})
    main._answer_cache.clear()
    r = TestClient(main.app).post("/ask/stream", json={"question": "ما نص المادة 1؟"})

    assert "event: error" in r.text
    error = next(block for block in r.text.split("\n\n") if block.startswith("event: error"))
    assert json.loads(error.split("data: ", 1)[1]) == {
        "status": 503,
        "detail": "deliberate pipeline failure",
    }

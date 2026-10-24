"""Run the REAL API (routing, retrieval over the real corpus, critic, cache, metrics) with a
deterministic stub embedder + stub LLM and an embedded Qdrant, for load-testing WITHOUT Ollama /
model weights. Latency therefore excludes real LLM generation: it measures the service's own
overhead and concurrency behaviour, not production answer latency.

    python scripts/loadtest/loadtest_server_stub.py --port 8001
"""
import argparse
import hashlib
import json
import tempfile

import uvicorn

DIM = 256

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8001)
    args = ap.parse_args()

    from agents.orchestrator import Orchestrator
    from agents.retriever import RetrieverAgent
    from agents.writer import WriterAgent
    from api import main
    from core.config import settings
    from core.models import Chunk, Citation, RagAnswer
    from rag.embedding.embedder import BaseEmbedder
    from rag.indexing.vector_store import QdrantVectorStore
    from rag.ingestion.legal_arabic_text import prepare_for_embedding
    from rag.reranking.reranker import PassThroughReranker
    from rag.retrieval.hybrid import HybridRetriever
    from rag.retrieval.sparse import BM25Index
    from rag.validation.critic import CriticAgent
    from tools.search_documents import SearchDocumentsTool

    class Emb(BaseEmbedder):
        def _v(self, t: str) -> list[float]:
            v = [0.0] * DIM
            for tok in prepare_for_embedding(t).split():
                v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM] += 1.0
            n = sum(x * x for x in v) ** 0.5 or 1.0
            return [x / n for x in v]

        def embed_documents(self, texts):
            return [self._v(t) for t in texts]

        def embed_query(self, text):
            return self._v(text)

    class StubLLM:
        def generate(self, question, contexts, feedback=None):
            top = contexts[0].chunk
            n = int(top.metadata["number"])
            return RagAnswer(
                question=question, answer=f"وفقا للمادة {n}: {top.text[:300]}",
                contexts=[c.chunk.text for c in contexts],
                citations=[Citation(article_id=top.article_ids[0], article_number=n, snippet="")],
            )

    chunks = [Chunk(**c) for c in json.load(open(settings.chunks_path, encoding="utf-8"))]
    emb = Emb()
    store = QdrantVectorStore(collection="load", dimension=DIM, path=tempfile.mkdtemp())
    store.upsert(chunks, emb.embed_documents([c.text for c in chunks]))
    tool = SearchDocumentsTool(
        HybridRetriever(emb, store, BM25Index(chunks)), PassThroughReranker(), 20, 5
    )
    main._pipeline.update(
        orchestrator=Orchestrator(RetrieverAgent(tool, None), WriterAgent(StubLLM()), CriticAgent())
    )
    uvicorn.run(main.app, host="127.0.0.1", port=args.port, log_level="warning")

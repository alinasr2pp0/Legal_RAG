"""Dense retrieval: embed the query and search the vector store."""

from __future__ import annotations

from core.models import ScoredChunk
from rag.embedding.embedder import BaseEmbedder
from rag.indexing.vector_store import BaseVectorStore


class DenseRetriever:
    def __init__(self, embedder: BaseEmbedder, vector_store: BaseVectorStore) -> None:
        self.embedder = embedder
        self.vector_store = vector_store

    def search(self, embedding_text: str, top_k: int) -> list[ScoredChunk]:
        return self.vector_store.query(self.embedder.embed_query(embedding_text), top_k=top_k)

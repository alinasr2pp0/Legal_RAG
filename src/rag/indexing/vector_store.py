"""Vector store backends. BaseVectorStore keeps the store swappable.

* QdrantVectorStore - embedded (local folder) or server mode, no account

Third-party clients are imported lazily inside the constructors.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

from core.config import settings
from core.models import Chunk, ScoredChunk


class BaseVectorStore(ABC):
    index_name: str = ""

    @abstractmethod
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...

    @abstractmethod
    def query(self, embedding: list[float], top_k: int) -> list[ScoredChunk]: ...

    def count(self) -> int:
        return -1


def _clean_metadata(chunk: Chunk) -> dict[str, Any]:
    # None values (book/part/chapter are frequently None) are dropped from the payload.
    return {k: v for k, v in chunk.metadata.items() if v is not None}


class QdrantVectorStore(BaseVectorStore):
    """Qdrant in embedded mode (a local folder, no server) or server mode."""

    def __init__(
        self,
        collection: str | None = None,
        dimension: int | None = None,
        path: str | None = None,
        url: str | None = None,
    ) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self.index_name = collection or settings.qdrant_collection
        server_url = url if url is not None else settings.qdrant_url
        if server_url:
            self.client = QdrantClient(url=server_url)
        else:
            self.client = QdrantClient(path=path or settings.qdrant_path)

        size = dimension or settings.embedding_dimension
        if self.client.collection_exists(self.index_name):
            existing = self.client.get_collection(self.index_name).config.params.vectors
            existing_size = getattr(existing, "size", None)
            if existing_size is not None and existing_size != size:
                raise RuntimeError(
                    f"Qdrant collection {self.index_name!r} has dimension {existing_size} "
                    f"but EMBEDDING_DIMENSION={size}. Re-index with "
                    "`python scripts/data/build_index.py --recreate`."
                )
        else:
            self.client.create_collection(
                self.index_name, vectors_config=VectorParams(size=size, distance=Distance.COSINE)
            )

    def recreate(self, dimension: int | None = None) -> None:
        """Drop and recreate the collection (used by build_index --recreate)."""
        from qdrant_client.models import Distance, VectorParams

        self.client.delete_collection(self.index_name)
        self.client.create_collection(
            self.index_name,
            vectors_config=VectorParams(
                size=dimension or settings.embedding_dimension, distance=Distance.COSINE
            ),
        )

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        # Qdrant ids must be uint or UUID: derive a stable UUID from chunk_id.
        return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        from qdrant_client.models import PointStruct

        points = []
        for chunk, vector in zip(chunks, embeddings, strict=True):
            payload = _clean_metadata(chunk)
            payload.update(text=chunk.text, chunk_id=chunk.chunk_id)
            points.append(
                PointStruct(id=self._point_id(chunk.chunk_id), vector=vector, payload=payload)
            )
        self.client.upsert(self.index_name, points=points)

    def query(self, embedding: list[float], top_k: int) -> list[ScoredChunk]:
        result = self.client.query_points(
            self.index_name, query=embedding, limit=top_k, with_payload=True
        )
        scored: list[ScoredChunk] = []
        for point in result.points:
            payload = dict(point.payload or {})
            text = str(payload.pop("text", ""))
            chunk_id = str(payload.pop("chunk_id", point.id))
            chunk = Chunk(
                chunk_id=chunk_id,
                text=text,
                article_ids=[str(payload.get("article_id", ""))],
                metadata=payload,
            )
            scored.append(ScoredChunk(chunk=chunk, score=float(point.score)))
        return scored

    def count(self) -> int:
        return int(self.client.count(self.index_name).count)

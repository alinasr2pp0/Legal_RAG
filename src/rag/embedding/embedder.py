"""Embedding backends. BaseEmbedder makes the provider swappable.

* LocalEmbedder - sentence-transformers (default intfloat/multilingual-e5-small), runs offline

Heavy third-party imports happen lazily inside the constructors so that
importing this module (and running unit tests / CI) stays cheap.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.config import settings


class BaseEmbedder(ABC):
    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...


# E5-family models are trained with instruction prefixes; skipping them hurts retrieval quality.
_E5_PREFIXES = ("query: ", "passage: ")


def prefixes_for(model_name: str, force: bool | None = None) -> tuple[str, str]:
    """(query_prefix, document_prefix) for a sentence-transformers model name or local folder.

    ``force`` (EMBEDDING_E5_PREFIXES=true/false) overrides the name check, for a local folder
    whose name does not contain "e5".
    """
    use = force if force is not None else "e5" in model_name.lower()
    return _E5_PREFIXES if use else ("", "")


class LocalEmbedder(BaseEmbedder):
    """Offline embeddings via sentence-transformers (e.g. intfloat/multilingual-e5-small, 384-d,
    or BAAI/bge-m3, 1024-d). E5 query/passage prefixes are added automatically."""

    def __init__(self, model_name: str | None = None, batch_size: int | None = None) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name or settings.local_embedding_model
        self.batch_size = batch_size or settings.local_embedding_batch_size
        self.query_prefix, self.doc_prefix = prefixes_for(
            self.model_name, settings.embedding_e5_prefixes
        )
        self.model: Any = SentenceTransformer(self.model_name)

    @property
    def dimension(self) -> int:
        return int(self.model.get_sentence_embedding_dimension())

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [[float(x) for x in v] for v in vectors]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode([self.doc_prefix + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([self.query_prefix + text])[0]

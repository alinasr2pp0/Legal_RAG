"""Caching layer: query-embedding cache and final-answer cache.

Why: every /ask call pays for (1) a query embedding, (2) Qdrant +
BM25 retrieval, (3) Voyage reranking, (4) an LLM call. Legal
questions repeat heavily (same article asked in slightly different
wording), so caching the embedding and the final answer removes the most
expensive steps for repeated questions.

Cache keys use aggressive Arabic normalization (hamza/alef/yaa/taa-marbuta
unified, tashkeel stripped) + whitespace collapse + lowercase, so
"ما هي شروط العقد؟" and "ما هى شروط العقد ؟" hit the same entry.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Generic, TypeVar

from rag.embedding.embedder import BaseEmbedder
from rag.ingestion.normalizer import ArabicNormalizer

T = TypeVar("T")

_normalizer = ArabicNormalizer()


def normalize_key(text: str) -> str:
    cleaned = _normalizer.aggressive(text).lower()
    # drop punctuation that doesn't change meaning, collapse spaces
    for ch in "؟?!.,،؛;:\"'()[]":
        cleaned = cleaned.replace(ch, " ")
    return " ".join(cleaned.split())


class TTLCache(Generic[T]):
    """Thread-safe LRU cache with per-entry TTL and hit/miss counters."""

    def __init__(self, max_entries: int = 1024, ttl_seconds: float = 3600.0) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._data: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> T | None:
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self.misses += 1
                return None
            stored_at, value = entry
            if now - stored_at > self.ttl_seconds:
                del self._data[key]
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: T) -> None:
        with self._lock:
            self._data[key] = (time.monotonic(), value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = 0
            self.misses = 0

    def __len__(self) -> int:
        return len(self._data)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


class CachedEmbedder(BaseEmbedder):
    """Wraps any embedder; caches *query* embeddings only (documents are
    embedded once at index time, so caching them has no benefit)."""

    def __init__(
        self,
        inner: BaseEmbedder,
        cache: TTLCache[list[float]],
        on_event: Callable[[bool], None] | None = None,
    ) -> None:
        self.inner = inner
        self.cache = cache
        self.on_event = on_event  # called with hit=True/False (used for metrics)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.inner.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        key = normalize_key(text)
        cached = self.cache.get(key)
        if self.on_event:
            self.on_event(cached is not None)
        if cached is not None:
            return cached
        vector = self.inner.embed_query(text)
        self.cache.set(key, vector)
        return vector

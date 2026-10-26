"""Reranking of the fused hybrid retrieval results (Voyage Rerank API, or pass-through)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from core.config import settings
from core.models import ScoredChunk

logger = logging.getLogger(__name__)


class BaseReranker(ABC):
    @abstractmethod
    def rerank(
        self, query: str, candidates: list[ScoredChunk], top_k: int
    ) -> list[ScoredChunk]: ...


class VoyageReranker(BaseReranker):
    """Hosted reranking through the Voyage Rerank API.

    Needs your own ``VOYAGE_API_KEY`` (kept in ``.env``). Only the (PII-masked) query and the
    retrieved Civil Code article texts are sent; private case-document excerpts and web
    snippets are never sent -- they keep their place after the scored candidates.
    Any API failure raises, and the factory / caller decides whether to degrade to the fused order.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.voyage_api_key
        if not self.api_key:
            raise RuntimeError("VOYAGE_API_KEY is empty (set it in your own .env)")
        self.model_name = model or settings.voyage_rerank_model
        self.url = (base_url or settings.voyage_base_url).rstrip("/") + "/rerank"
        self.timeout = timeout if timeout is not None else settings.voyage_timeout_seconds

    def rerank(self, query: str, candidates: list[ScoredChunk], top_k: int) -> list[ScoredChunk]:
        import httpx

        sendable = [c for c in candidates if c.chunk.metadata.get("source") not in _PRIVATE]
        private = [c for c in candidates if c.chunk.metadata.get("source") in _PRIVATE]
        if not sendable:
            return candidates[:top_k]
        try:
            resp = httpx.post(
                self.url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "query": query,
                    "documents": [c.chunk.text for c in sendable],
                    "model": self.model_name,
                    "top_k": min(top_k, len(sendable)),
                    "truncation": True,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            # If reranker is required, raise custom error; otherwise fallback to original order
            if settings.reranker_required:
                from rag.reranking.exceptions import RerankerUnavailableError
                raise RerankerUnavailableError(str(exc)) from exc
            logger.warning(
                "Voyage reranker request failed (%s) – falling back to fused order.",
                exc,
            )
            return candidates[:top_k]
        ranked: list[ScoredChunk] = []
        for item in resp.json()["data"]:
            chunk = sendable[int(item["index"])].chunk
            ranked.append(ScoredChunk(chunk=chunk, score=float(item["relevance_score"])))
        ranked.sort(key=lambda sc: sc.score, reverse=True)
        return (ranked + private)[:top_k]


_PRIVATE = {"case", "web"}


class PassThroughReranker(BaseReranker):
    """No-op reranker (keeps the fused RRF order) for machines too small to
    run a cross-encoder; enable with RERANKER_ENABLED=false."""

    def rerank(self, query: str, candidates: list[ScoredChunk], top_k: int) -> list[ScoredChunk]:
        return candidates[:top_k]

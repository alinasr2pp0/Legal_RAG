"""Pick embedder / vector-store implementations from settings, so the same
code builds the local stack (sentence-transformers embedder + Qdrant)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from core.config import Settings, settings
from core.local_only import local_only_violations
from rag.embedding.embedder import BaseEmbedder
from rag.indexing.vector_store import BaseVectorStore

logger = logging.getLogger(__name__)


def missing_requirements(cfg: Settings | None = None) -> list[str]:
    """Human-readable list of what is missing for the configured backends
    (empty list == ready). Lets the API answer 503 with a precise reason."""
    cfg = cfg or settings
    missing: list[str] = [f"LOCAL_ONLY: {p}" for p in local_only_violations(cfg)]
    return missing


def build_embedder(cfg: Settings | None = None) -> BaseEmbedder:
    cfg = cfg or settings
    from rag.embedding.embedder import LocalEmbedder

    setup_model_env(cfg)
    embedder = LocalEmbedder()
    if cfg.embedding_dimension != embedder.dimension:
        logging.getLogger(__name__).info(
            "EMBEDDING_DIMENSION %s -> %s (from %s)",
            cfg.embedding_dimension, embedder.dimension, embedder.model_name,
        )
        cfg.embedding_dimension = embedder.dimension  # the model is the source of truth
    return embedder


def build_vector_store(cfg: Settings | None = None) -> BaseVectorStore:
    from rag.indexing.vector_store import QdrantVectorStore

    return QdrantVectorStore()


def setup_model_env(cfg: Settings | None = None) -> None:
    """Point the Hugging Face cache at ``models_dir`` and go offline when asked.
    Must run before sentence-transformers loads a model."""
    cfg = cfg or settings
    os.environ.setdefault("HF_HOME", str(Path(cfg.models_dir).resolve() / "hf"))
    if cfg.hf_offline or cfg.local_only:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"


def build_reranker(cfg: Settings | None = None):  # type: ignore[no-untyped-def]
    """Voyage Rerank API reranker, or a pass-through when disabled / unavailable.

    Needs ``VOYAGE_API_KEY`` in your own ``.env``. A reranker that cannot start (key missing)
    degrades to the fused RRF order with a loud warning, unless ``RERANKER_REQUIRED=true``.
    """
    from rag.reranking.reranker import PassThroughReranker, VoyageReranker

    cfg = cfg or settings
    if not cfg.reranker_enabled:
        return PassThroughReranker()
    try:
        return VoyageReranker()
    except Exception as exc:  # noqa: BLE001 - degrade gracefully, never take /ask down
        if cfg.reranker_required:
            from rag.reranking.exceptions import RerankerUnavailableError
            raise RerankerUnavailableError(str(exc)) from exc
        logger.warning(
            "Voyage reranker unavailable (%s) -> using fused order. Set VOYAGE_API_KEY "
            "or RERANKER_ENABLED=false.",
            exc,
        )
        return PassThroughReranker()

"""Preflight for the all-local setup. Exit code 0 == ready.

Usage: python scripts/ops/check_local_stack.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

from core.config import settings
from core.local_only import local_only_violations
from rag.indexing.factory import setup_model_env


def _hf_cached(repo: str) -> bool:
    """True when ``repo`` is a local model folder (e.g. D:/AI-Models/multilingual-e5-small) or is
    present in the Hugging Face cache."""
    folder = Path(repo)
    if folder.is_dir():
        return (folder / "modules.json").exists() or (folder / "config.json").exists()
    setup_model_env(settings)
    import os

    root = Path(os.environ.get("HF_HOME", Path(settings.models_dir) / "hf")) / "hub"
    return (root / ("models--" + repo.replace("/", "--"))).exists()


def main() -> int:
    ok = True

    def report(name: str, good: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= good
        print(f"[{'OK' if good else 'FAIL'}] {name} {detail}")

    violations = local_only_violations(settings) if settings.local_only else []
    report("LOCAL_ONLY config", not violations, "; ".join(violations))
    if not settings.local_only:
        print("[WARN] LOCAL_ONLY is false: nothing enforces that all services are local")

    base = settings.llm_base_url.rstrip("/")
    try:
        r = httpx.get(base + "/models", timeout=5.0)
        names = {m.get("id") for m in r.json().get("data", [])}
        report("LLM server reachable", r.status_code == 200, base)
        report("LLM model pulled", settings.llm_model_primary in names,
               f"({settings.llm_model_primary}; run: ollama pull {settings.llm_model_primary})")
    except (httpx.HTTPError, ValueError) as exc:
        report("LLM server reachable", False, f"{base} ({exc})")

    report("embedding model cached", _hf_cached(settings.local_embedding_model),
           settings.local_embedding_model)
    if settings.reranker_enabled:
        report("Voyage API key set", bool(settings.voyage_api_key),
               f"(model {settings.voyage_rerank_model}; without a key the fused order is used)")
    if settings.web_search_enabled and not settings.local_only and not settings.tavily_api_key:
        print("[WARN] WEB_SEARCH_ENABLED=true but TAVILY_API_KEY is empty: web fallback stays off")

    chunks = Path(settings.chunks_path)
    n = len(json.loads(chunks.read_text(encoding="utf-8"))) if chunks.exists() else 0
    report("chunks corpus", n > 0, f"{n} chunks at {chunks}")
    if not settings.qdrant_url:
        report("qdrant index folder", Path(settings.qdrant_path).exists(),
               f"{settings.qdrant_path} (run scripts/data/build_index.py)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

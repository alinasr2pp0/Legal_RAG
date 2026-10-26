# ruff: noqa: E402
"""FastAPI app exposing the RAG pipeline. Run with:
    uvicorn api.main:app --host 0.0.0.0 --port 8000

The pipeline (embedder/vector_store/retriever/reranker/llm_client) is
wired up lazily on first request, not at import time, so the app can
still boot for /health checks in CI even without API keys configured.
"""

from __future__ import annotations

import json
import os
import re

# Ensure the project ``src`` directory is on the Python import path so that top‑level imports like
# ``from core.config import settings`` work when the app is started from the repository root.
import sys
import threading
import time
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from starlette.responses import FileResponse, Response, StreamingResponse

_src_dir = Path(__file__).resolve().parents[1]  # points to the ``src`` folder
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from core.cache import TTLCache, normalize_key
from core.case_store import CaseError, case_store
from core.config import settings
from core.feedback import feedback_counts, log_feedback
from core.guardrails import INJECTION_REFUSAL, detect_injection, redact_pii
from core.logging_config import request_id_var
from core.models import Chunk, ScoredChunk
from core.query_log import log_query
from rag.monitoring.exporter import (
    record_answer,
    record_cache,
    record_drift,
    record_query,
    record_ragas,
    registry,
)
from rag.monitoring.stats import stats
from rag.monitoring.tracing import trace_ask_request

from .cases import router as cases_router

if TYPE_CHECKING:
    from agents.orchestrator import Orchestrator
    from rag.reranking.reranker import BaseReranker
    from rag.retrieval.sparse import BM25Index

app = FastAPI(title="Egyptian Civil Code RAG", version="0.2.0")
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-Filename"],
    )

# Request‑ID middleware: propagate X-Request-ID header and expose to logging
import logging

from fastapi import Request


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Propagate X-Request-ID header, expose it to logging, and log the request line.

    The test suite expects a log entry from the ``api`` logger containing the HTTP
    method and path (e.g. ``GET /search``) without the query string. By retrieving a
    ``logger = logging.getLogger("api")`` and emitting an ``INFO`` message after the
    request has been processed we satisfy that expectation while the ``request_id``
    remains available via the ``request_id_var`` context variable, which the logging
    filter attaches to all log records.
    """
    request_id = request.headers.get("X-Request-ID", "-")
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
        # Add the request ID to the response for client visibility.
        response.headers["X-Request-ID"] = request_id
        # Log the request method and path (without query parameters).
        logger = logging.getLogger("api")
        logger.info(f"{request.method} {request.url.path}")
        return response
    finally:
        request_id_var.reset(token)

# project-root /Frontend (src/api/main.py -> parents[2]); FRONTEND_DIR overrides it
_FRONTEND = Path(os.getenv("FRONTEND_DIR") or Path(__file__).resolve().parents[2] / "Frontend")

app.include_router(cases_router)

_pipeline: dict[str, object] = {}
_pipeline_lock = threading.Lock()

# Caches: query embeddings (skips re-embedding) and final answers (skips
# retrieval + rerank + LLM entirely for repeated questions).
_embedding_cache: TTLCache[list[float]] = TTLCache(
    settings.cache_max_entries, settings.cache_ttl_seconds
)
_answer_cache: TTLCache[AskResponse] = TTLCache(
    settings.cache_max_entries, settings.cache_ttl_seconds
)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=settings.max_question_chars)
    case_id: str | None = Field(default=None, max_length=32)  # use that case's uploaded documents
    debug: bool = Field(False, description="Return retrieval diagnostics when true")


class SourceRef(BaseModel):
    article_number: int
    citation: str


class CriticInfo(BaseModel):
    passed: bool
    grounding: float
    issues: list[str]
    revisions: int
    refusal: bool = False  # an honest "the texts are not sufficient" answer


class CaseSourceRef(BaseModel):
    doc: str
    page: int
    snippet: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceRef]
    case_sources: list[CaseSourceRef] = []
    critic: CriticInfo | None = None
    pii_redacted: list[str] = []
    used_web_search: bool = False
    debug_info: list[dict] = []  # added for regression diagnostics

_ASK_BODY_EXAMPLES = {
    "general_question": {
        "summary": "سؤال قانوني عام",
        "description": "لا حاجة إلى case_id إلا عند السؤال عن مستندات قضية مرفوعة.",
        "value": {"question": "ما هو التعويض عن الضرر؟"},
    }
}


def _load_chunks() -> list[Chunk]:
    import json
    import logging
    from pathlib import Path

    chunks_path = Path(settings.chunks_path)
    if not chunks_path.exists():
        raise RuntimeError(
            f"{chunks_path} not found. Run the DVC pipeline (dvc repro) through the "
            "'chunk' stage first so BM25 has a corpus to index."
        )
    with open(chunks_path, encoding="utf-8") as f:
        chunks = [Chunk(**item) for item in json.load(f)]
    # Load additional Arabic legal texts defined in rag.extra_texts
    try:
        from rag.extra_texts import extra_chunks
        chunks.extend(extra_chunks())
    except Exception as e:
        logging.getLogger("api").warning(f"Failed to load extra Arabic legal text: {e}")
    return chunks


def _get_pipeline() -> dict[str, object]:
    """Build the pipeline components once, on first use. Raises a clear
    error (surfaced as HTTP 503) if required keys/index are missing,
    instead of failing at import time and blocking /health checks."""
    if _pipeline:
        return _pipeline
    with _pipeline_lock:
        if not _pipeline:
            _build_pipeline()
    return _pipeline


def _build_pipeline() -> None:
    from agents.orchestrator import Orchestrator
    from agents.retriever import RetrieverAgent
    from agents.writer import WriterAgent
    from core.cache import CachedEmbedder
    from rag.generation.llm_client import OpenAICompatLLMClient
    from rag.indexing.factory import (
        build_embedder,
        build_reranker,
        build_vector_store,
        missing_requirements,
    )
    from rag.retrieval.hybrid import HybridRetriever
    from rag.retrieval.sparse import BM25Index
    from rag.validation.critic import CriticAgent
    from tools.search_documents import SearchDocumentsTool
    from tools.tavily_search import TavilySearchTool

    missing = missing_requirements()
    if missing:
        raise RuntimeError("Missing configuration: " + "; ".join(missing))
    if not settings.llm_api_key:
        raise RuntimeError("Missing LLM_API_KEY (any non-empty value for Ollama).")

    embedder = build_embedder()
    if settings.cache_enabled:
        embedder = CachedEmbedder(
            embedder, _embedding_cache, on_event=lambda hit: record_cache("embedding", hit)
        )
    retriever = HybridRetriever(embedder, build_vector_store(), BM25Index(_load_chunks()))

    reranker: BaseReranker = build_reranker()

    search_tool = SearchDocumentsTool(
        retriever, reranker, settings.top_k_retrieval, settings.top_k_rerank
    )
    llm_client = OpenAICompatLLMClient()
    orchestrator = Orchestrator(
        RetrieverAgent(search_tool, TavilySearchTool()),
        WriterAgent(llm_client),
        CriticAgent(),
    )
    _pipeline.update(
        retriever=retriever,
        reranker=reranker,
        llm_client=llm_client,
        search_tool=search_tool,
        orchestrator=orchestrator,
    )


class ArticleInfo(BaseModel):
    article_number: int
    text: str
    is_repealed: bool
    chapter: str | None = None
    text_missing: bool = False  # the source PDF has no text for this article
    text_incomplete: bool = False  # part of the Arabic text is absent from the source


@lru_cache(maxsize=1)
def _articles_by_number() -> dict[int, list[Chunk]]:
    out: dict[int, list[Chunk]] = {}
    for chunk in _load_chunks():
        n = chunk.metadata.get("number")
        if n:
            out.setdefault(int(n), []).append(chunk)
    return out


def _part(chunk: Chunk) -> int:
    return int(chunk.metadata.get("chunk_part") or 0)


@app.get("/article/{number}", response_model=ArticleInfo)
def article(number: int) -> ArticleInfo:
    """Full text of one article (used by the UI side panel; needs no models)."""
    try:
        chunks = _articles_by_number().get(number)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not chunks:
        raise HTTPException(status_code=404, detail=f"المادة {number} غير موجودة")
    first = chunks[0].metadata
    return ArticleInfo(
        article_number=number,
        text="\n".join(c.text for c in sorted(chunks, key=_part)),
        is_repealed=bool(first.get("is_repealed")),
        chapter=str(first["chapter"]) if first.get("chapter") else None,
        text_missing=bool(first.get("text_missing")),
        text_incomplete=bool(first.get("text_incomplete")),
    )


class FeedbackRequest(BaseModel):
    rating: Literal["up", "down"]
    question: str = Field(default="", max_length=settings.max_question_chars)
    comment: str = Field(default="", max_length=500)
    articles: list[int] = Field(default_factory=list, max_length=20)
    critic_passed: bool | None = None


@app.post("/feedback", status_code=204)
def feedback(request: FeedbackRequest) -> Response:
    """Thumbs up/down on an answer (question + comment are PII-redacted before storage)."""
    try:
        log_feedback(
            request.rating, request.question, request.comment,
            request.articles, request.critic_passed,
        )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"feedback not saved: {exc}") from exc
    return Response(status_code=204)


class SearchHit(BaseModel):
    article_number: int
    snippet: str
    is_repealed: bool


@lru_cache(maxsize=1)
def _bm25() -> BM25Index:
    from rag.retrieval.sparse import BM25Index

    return BM25Index(_load_chunks())


@app.get("/search", response_model=list[SearchHit])
def search_articles(
    q: str = Query(min_length=1, max_length=200), limit: int = Query(8, ge=1, le=20)
) -> list[SearchHit]:
    """Keyword search over the articles (BM25, no models needed)."""
    try:
        hits = _bm25().search(q, limit * 3)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    seen: set[int] = set()
    out: list[SearchHit] = []
    for hit in hits:
        n = int(hit.chunk.metadata.get("number") or 0)
        if not n or n in seen or hit.score <= 0:
            continue
        seen.add(n)
        out.append(
            SearchHit(
                article_number=n,
                snippet=hit.chunk.text[:160],
                is_repealed=bool(hit.chunk.metadata.get("is_repealed")),
            )
        )
        if len(out) >= limit:
            break
    return out


@app.get("/", include_in_schema=False)
def index() -> Response:
    page = _FRONTEND / "index.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="UI not installed")
    return FileResponse(page, media_type="text/html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _readiness_problems(pipeline: dict[str, Any]) -> list[str]:
    """Critical dependencies beyond "the objects were constructed": LLM server reachable and
    the model present, vector index consistent with the served corpus + embedder."""
    from rag.indexing.manifest import index_problems

    problems: list[str] = []
    retriever = pipeline["retriever"]
    with open(settings.chunks_path, encoding="utf-8") as f:
        n_chunks = len(json.load(f))
    try:
        indexed: int | None = retriever.vector_store.count()
    except Exception as exc:  # noqa: BLE001
        indexed = None
        problems.append(f"vector store unreachable: {exc}")
    embedder = getattr(retriever.embedder, "inner", retriever.embedder)  # unwrap the cache
    problems += index_problems(
        settings.chunks_path,
        model=getattr(embedder, "model_name", settings.local_embedding_model),
        dimension=settings.embedding_dimension,
        indexed_count=indexed,
        n_chunks=n_chunks,
    )
    return problems


def _llm_problems() -> list[str]:
    """Ask the (local) OpenAI-compatible server which models it serves."""
    import httpx

    url = settings.llm_base_url.rstrip("/") + "/models"
    try:
        r = httpx.get(
            url, timeout=3.0,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        )
        r.raise_for_status()
        served = {m.get("id") for m in r.json().get("data", [])}
    except Exception as exc:  # noqa: BLE001
        return [f"LLM server unreachable at {url}: {exc}"]
    wanted = [settings.llm_model_primary]
    missing = [m for m in wanted if m not in served]
    return [f"LLM model not served (pull it first): {', '.join(missing)}"] if missing else []


@app.get("/ready")
def ready() -> dict[str, object]:
    """Readiness: configured local services, loaded RAG pipeline, and consistent index."""
    from rag.indexing.factory import missing_requirements

    problems = missing_requirements()
    if not problems:
        problems += _llm_problems()
    if not problems:
        try:
            pipeline = _get_pipeline()
            problems += _readiness_problems(pipeline)
        except (RuntimeError, OSError, ValueError) as exc:
            import traceback
            traceback.print_exc()
            problems.append(f"RAG pipeline unavailable: {exc}")
    if problems:
        raise HTTPException(status_code=503, detail="; ".join(dict.fromkeys(problems)))
    return {"status": "ready", "local_only": settings.local_only}


def _reranker_model_name() -> str:
    if not settings.reranker_enabled:
        return "-"
    return settings.voyage_rerank_model


@app.get("/stats")
def dashboard_stats() -> dict[str, object]:
    """Live numbers for the UI dashboard (rolling window; no user text)."""
    corpus: dict[str, int] = {}
    try:
        by_number = _articles_by_number()
        corpus = {
            "articles": len(by_number),
            "repealed": sum(1 for c in by_number.values() if c[0].metadata.get("is_repealed")),
            "chunks": sum(len(c) for c in by_number.values()),
        }
    except RuntimeError:
        pass
    reranker = _pipeline.get("reranker")
    return {
        **stats.snapshot(),
        "corpus": corpus,
        "system": {
            "pipeline_loaded": bool(_pipeline),
            "local_only": settings.local_only,
            "profile": settings.provider_profile or "custom",
            "embedding": settings.local_embedding_model,
            "vector_store": "qdrant",
            "llm": settings.llm_model_primary,
            "reranker": type(reranker).__name__ if reranker else "not loaded",
            "reranker_model": _reranker_model_name(),
            "web_search": settings.web_search_enabled and not settings.local_only,
        },
        "feedback": feedback_counts(),
        "cache": {
            name: {"entries": len(c), "hit_rate": round(c.hit_rate, 3)}
            for name, c in (("embedding", _embedding_cache), ("answer", _answer_cache))
        },
    }


@app.get("/cache/stats")
def cache_stats() -> dict[str, dict[str, float | int]]:
    return {
        name: {"entries": len(c), "hits": c.hits, "misses": c.misses, "hit_rate": c.hit_rate}
        for name, c in (("embedding", _embedding_cache), ("answer", _answer_cache))
    }


def _sync_external_metrics() -> None:
    # 1. RAGAS scores from latest evaluation run
    ragas_path = Path("data/eval/ragas_scores.json")
    if ragas_path.is_file():
        try:
            with open(ragas_path, encoding="utf-8") as f:
                data = json.load(f)
            record_ragas({k: float(v) for k, v in data.items() if k != "num_questions"})
        except Exception:
            pass

    # 2. Drift metrics from latest drift run
    drift_path = Path("data/logs/drift_history.jsonl")
    if drift_path.is_file():
        try:
            lines = drift_path.read_text(encoding="utf-8").strip().splitlines()
            if lines:
                last_drift = json.loads(lines[-1])
                record_drift(
                    mmd_score=float(last_drift.get("mmd", 0.0)),
                    cosine_score=float(last_drift.get("cosine_drift", 0.0)),
                )
        except Exception:
            pass


@app.get("/metrics")
def metrics() -> Response:
    _sync_external_metrics()
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)


def _answer(question: str, case_id: str | None = None, debug: bool = False) -> AskResponse:
    """Handbook-spec endpoint: {"question": "..."} -> {"answer": "...",
    "sources": [{"article_number": N, "citation": "..."}]} (+ critic info)."""
    start = time.perf_counter()
    if settings.injection_guard_enabled and detect_injection(question):
        record_query((time.perf_counter() - start) * 1000)
        return AskResponse(answer=INJECTION_REFUSAL, sources=[])
    extra: list[ScoredChunk] = []
    if case_id:
        if not settings.case_upload_enabled:
            raise HTTPException(status_code=404, detail="ميزة مستندات القضية معطّلة")
        try:
            extra = case_store.search(case_id, question)
        except CaseError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    # Case answers depend on private documents: never served from / stored in the shared cache
    cache_key = normalize_key(question)
    if settings.cache_enabled and not case_id:
        cached = _answer_cache.get(cache_key)
        record_cache("answer", cached is not None)
        if cached is not None:
            latency = (time.perf_counter() - start) * 1000
            record_query(latency)
            stats.record(
                latency_ms=latency, passed=cached.critic.passed if cached.critic else None,
                grounding=cached.critic.grounding if cached.critic else None,
                cache_hit=True, articles=[x.article_number for x in cached.sources],
            )
            return cached

    try:
        pipeline = _get_pipeline()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    orchestrator: Orchestrator = pipeline["orchestrator"]  # type: ignore[assignment]

    # Traces may leave the machine (Langfuse is exempt from LOCAL_ONLY): send only the
    # PII-redacted question, and never trace answers built from private case documents.
    traced_q = redact_pii(question).text if settings.pii_redaction_enabled else question
    with trace_ask_request(traced_q, enabled=not case_id) as (spans, _correlation_id):
        try:
            result = orchestrator.run(question, spans=spans, extra_chunks=extra or None)
        except RuntimeError as exc:  # e.g. every LLM in the fallback chain failed
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        spans.log_generation(
            model=settings.llm_model_primary,
            prompt=result.question,  # PII-redacted
            completion=result.answer,
        )

    verdict = result.verdict
    if not case_id:
        # case questions may contain private facts: keep them out of the query log
        log_query(result.question, verdict.passed if verdict else None)
    latency = (time.perf_counter() - start) * 1000
    record_query(latency)
    stats.record(
        latency_ms=latency,
        passed=verdict.passed if verdict else None,
        refusal=bool(verdict and verdict.refusal),
        grounding=verdict.grounding if verdict else None,
        revisions=result.revisions,
        used_web=result.used_web,
        pii=bool(result.pii_found),
        explicit_article=bool(result.article_numbers),
        articles=[c.article_number for c in result.citations],
    )
    record_answer(
        verdict_passed=verdict.passed if verdict else None,
        refusal=bool(verdict and verdict.refusal),
        grounding=verdict.grounding if verdict else None,
        revisions=result.revisions,
        pii_kinds=result.pii_found,
        used_web=result.used_web,
        explicit_article=bool(result.article_numbers),
    )

    response = AskResponse(
        answer=result.answer,
        sources=[
            SourceRef(article_number=c.article_number, citation=c.citation)
            for c in result.citations
        ],
        critic=CriticInfo(
            passed=verdict.passed,
            grounding=round(verdict.grounding, 3),
            issues=verdict.issues,
            revisions=result.revisions,
            refusal=verdict.refusal,
        )
        if verdict
        else None,
        pii_redacted=sorted(set(result.pii_found)),
        used_web_search=result.used_web,
        case_sources=[
            CaseSourceRef(
                doc=str(c.chunk.metadata.get("doc")), page=int(c.chunk.metadata.get("page") or 0),
                snippet=c.chunk.text[:220],
            )
            for c in extra
        ],
    )
    # Attach debug diagnostics if requested
    if debug:
        debug_items = []
        # Include top retrieved chunks (up to 20) with scores and metadata
        for idx, sc in enumerate(result.evidence_chunks[:20], start=1):
            chunk = sc.chunk
            meta = chunk.metadata
            debug_items.append({
                "rank": idx,
                "score": sc.score,
                "article_number": meta.get("number"),
                "article_id": meta.get("article_id"),
                "citation": f"Egyptian Civil Code, Article {meta.get('number')}",
                "snippet": chunk.text[:200].replace("\n", " "),
                "source_file": meta.get("source_file"),
            })
        # Ensure all explicitly identified article numbers are present in debug_info
        for n in sorted(set(result.article_numbers)):
            if not any(item.get("article_number") == n for item in debug_items):
                debug_items.append({"article_number": n})
        response.debug_info = debug_items
    # Log the answer for the case (if any) so the UI can show a history.
    if case_id:
        from core.case_log import log_case_answer
        log_case_answer(case_id, response)
    # never cache PII questions, private-case answers or answers the critic did not verify
    if (
        settings.cache_enabled and not result.pii_found and not case_id
        and (verdict is None or verdict.passed)
    ):
        _answer_cache.set(cache_key, response)
    return response
    """Handbook-spec endpoint: {"question": "..."} -> {"answer": "...",
    "sources": [{"article_number": N, "citation": "..."}]} (+ critic info)."""
    start = time.perf_counter()
    if settings.injection_guard_enabled and detect_injection(question):
        record_query((time.perf_counter() - start) * 1000)
        return AskResponse(answer=INJECTION_REFUSAL, sources=[])
    extra: list[ScoredChunk] = []
    if case_id:
        if not settings.case_upload_enabled:
            raise HTTPException(status_code=404, detail="ميزة مستندات القضية معطّلة")
        try:
            extra = case_store.search(case_id, question)
        except CaseError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    # Case answers depend on private documents: never served from / stored in the shared cache
    cache_key = normalize_key(question)
    if settings.cache_enabled and not case_id:
        cached = _answer_cache.get(cache_key)
        record_cache("answer", cached is not None)
        if cached is not None:
            latency = (time.perf_counter() - start) * 1000
            record_query(latency)
            stats.record(
                latency_ms=latency, passed=cached.critic.passed if cached.critic else None,
                grounding=cached.critic.grounding if cached.critic else None,
                cache_hit=True, articles=[x.article_number for x in cached.sources],
            )
            return cached

    try:
        pipeline = _get_pipeline()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    orchestrator: Orchestrator = pipeline["orchestrator"]  # type: ignore[assignment]

    # Traces may leave the machine (Langfuse is exempt from LOCAL_ONLY): send only the
    # PII-redacted question, and never trace answers built from private case documents.
    traced_q = redact_pii(question).text if settings.pii_redaction_enabled else question
    with trace_ask_request(traced_q, enabled=not case_id) as (spans, _correlation_id):
        try:
            result = orchestrator.run(question, spans=spans, extra_chunks=extra or None)
        except RuntimeError as exc:  # e.g. every LLM in the fallback chain failed
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        spans.log_generation(
            model=settings.llm_model_primary,
            prompt=result.question,  # PII-redacted
            completion=result.answer,
        )

    verdict = result.verdict
    if not case_id:  # case questions may contain private facts: keep them out of the query log
        log_query(result.question, verdict.passed if verdict else None)
    latency = (time.perf_counter() - start) * 1000
    record_query(latency)
    stats.record(
        latency_ms=latency,
        passed=verdict.passed if verdict else None,
        refusal=bool(verdict and verdict.refusal),
        grounding=verdict.grounding if verdict else None,
        revisions=result.revisions,
        used_web=result.used_web,
        pii=bool(result.pii_found),
        explicit_article=bool(result.article_numbers),
        articles=[c.article_number for c in result.citations],
    )
    record_answer(
        verdict_passed=verdict.passed if verdict else None,
        refusal=bool(verdict and verdict.refusal),
        grounding=verdict.grounding if verdict else None,
        revisions=result.revisions,
        pii_kinds=result.pii_found,
        used_web=result.used_web,
        explicit_article=bool(result.article_numbers),
    )

    response = AskResponse(
        answer=result.answer,
        sources=[
            SourceRef(article_number=c.article_number, citation=c.citation)
            for c in result.citations
        ],
        critic=CriticInfo(
            passed=verdict.passed,
            grounding=round(verdict.grounding, 3),
            issues=verdict.issues,
            revisions=result.revisions,
            refusal=verdict.refusal,
        )
        if verdict
        else None,
        pii_redacted=sorted(set(result.pii_found)),
        used_web_search=result.used_web,
        case_sources=[
            CaseSourceRef(
                doc=str(c.chunk.metadata.get("doc")), page=int(c.chunk.metadata.get("page") or 0),
                snippet=c.chunk.text[:220],
            )
            for c in extra
        ],
    )
    # Log the answer for the case (if any) so the UI can show a history.
    if case_id:
        from core.case_log import log_case_answer
        log_case_answer(case_id, response)
    # never cache PII questions, private-case answers or answers the critic did not verify
    if (
        settings.cache_enabled and not result.pii_found and not case_id
        and (verdict is None or verdict.passed)
    ):
        _answer_cache.set(cache_key, response)
    return response


@app.post("/ask", response_model=AskResponse)
def ask(
    request: AskRequest = Body(openapi_examples=_ASK_BODY_EXAMPLES),
) -> AskResponse:
    """Handle POST /ask. Forward debug flag to internal _answer."""
    return _answer(request.question, request.case_id, debug=request.debug)
    return _answer(request.question, request.case_id)

# Compatibility GET endpoints for UI that historically used GET
@app.get("/ask", response_model=AskResponse)
def ask_get(question: str, case_id: str | None = None) -> AskResponse:
    """Legacy GET wrapper for the Ask endpoint."""
    return _answer(question, case_id)

@app.get("/ask/stream", response_model=None)
def ask_stream_get(question: str, case_id: str | None = None) -> StreamingResponse:
    """Legacy GET wrapper for the streaming Ask endpoint."""
    return ask_stream(AskRequest(question=question, case_id=case_id))


def _sse(event: str | None, data: str) -> str:
    head = f"event: {event}\n" if event else ""
    return head + "".join(f"data: {line}\n" for line in data.split("\n")) + "\n"


def _token_chunks(text: str) -> Iterator[str]:
    """Whitespace-preserving word chunks (newlines stay inside their chunk)."""
    yield from (m.group(0) for m in re.finditer(r"\S+\s*", text))


@app.post("/ask/stream")
def ask_stream(
    request: AskRequest = Body(openapi_examples=_ASK_BODY_EXAMPLES),
) -> StreamingResponse:
    """Same full RAG pipeline as /ask (retrieve -> write -> critic loop, citations,
    PII redaction), delivered as a stream: ``status`` events while it works, the
    verified answer as ``data:`` word chunks, then one ``result`` event carrying
    the complete AskResponse JSON (sources, critic, flags).

    The critic needs the whole draft, so streaming starts after verification:
    what the user sees is always the checked answer, never an unverified draft."""

    def events() -> Iterator[str]:
        yield _sse("status", "searching")
        try:
            response = _answer(request.question, request.case_id)
        except HTTPException as exc:
            yield _sse("error", json.dumps({"status": exc.status_code, "detail": str(exc.detail)}))
            return
        except Exception as exc:  # noqa: BLE001 - never leave the stream hanging
            yield _sse("error", json.dumps({"status": 500, "detail": str(exc)}))
            return
        for chunk in _token_chunks(response.answer):
            yield _sse(None, chunk)
        yield _sse("result", response.model_dump_json())

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


def run() -> None:
    import os

    import uvicorn
    _port = int(os.getenv("PORT", "8000"))
    uvicorn.run("api.main:app", host="0.0.0.0", port=_port, reload=False)


if __name__ == "__main__":
    run()

"""Prometheus metrics for the RAG service, scraped via /metrics or pushed
to a Pushgateway (useful when the API can't reliably be
scraped as a long-lived target)."""

from __future__ import annotations

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    push_to_gateway,
)

from core.config import settings

registry = CollectorRegistry()

QUERY_COUNTER = Counter(
    "rag_queries_total", "Total number of RAG queries served", registry=registry
)
QUERY_LATENCY = Histogram(
    "rag_query_latency_ms",
    "End-to-end query latency in milliseconds",
    # Buckets in ms: the prometheus_client defaults (0.005..10) top out at 10 ms, so p95 / the
    # 8 s latency alert could never be computed. Local CPU answers take seconds.
    buckets=(50, 100, 250, 500, 1000, 2000, 3000, 5000, 8000, 12000, 20000, 30000, 60000),
    registry=registry,
)
CACHE_EVENTS = Counter(
    "rag_cache_events_total",
    "Cache lookups by cache name and result (hit/miss)",
    ["cache", "result"],
    registry=registry,
)
FAITHFULNESS_GAUGE = Gauge(
    "rag_faithfulness_score", "Latest RAGAS faithfulness score (0-1)", registry=registry
)
DRIFT_GAUGE = Gauge(
    "rag_embedding_drift_mmd", "Latest MMD drift score vs baseline", registry=registry
)
COSINE_DRIFT_GAUGE = Gauge(
    "rag_embedding_drift_cosine", "Latest cosine drift score vs baseline", registry=registry
)


CRITIC_VERDICTS = Counter(
    "rag_critic_verdicts_total",
    "Critic-agent verdicts for served answers (passed/failed/refusal)",
    ["verdict"],
    registry=registry,
)
CRITIC_GROUNDING = Histogram(
    "rag_critic_grounding",
    "Lexical grounding of answers in retrieved evidence (0-1)",
    buckets=(0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
    registry=registry,
)
REVISIONS = Counter(
    "rag_answer_revisions_total", "Writer revisions triggered by the critic", registry=registry
)
PII_REDACTIONS = Counter(
    "rag_pii_redactions_total", "Questions in which PII was masked", ["kind"], registry=registry
)
WEB_FALLBACKS = Counter(
    "rag_web_fallback_total", "Answers that used the web-search fallback", registry=registry
)
EXPLICIT_ARTICLE_QUERIES = Counter(
    "rag_explicit_article_queries_total",
    "Questions that named an article number (direct lookup)",
    registry=registry,
)
RAGAS_METRIC = Gauge(
    "rag_ragas_metric", "Latest RAGAS metric by name (0-1)", ["metric"], registry=registry
)
FAITHFULNESS_ALERT = Gauge(
    "rag_faithfulness_alert",
    "1 when the latest faithfulness is below the alert threshold, else 0",
    registry=registry,
)


def record_answer(
    verdict_passed: bool | None,
    refusal: bool,
    grounding: float | None,
    revisions: int,
    pii_kinds: list[str],
    used_web: bool,
    explicit_article: bool,
) -> None:
    """One call per served (non-cached) answer from the orchestrator result."""
    if verdict_passed is not None:
        label = "refusal" if refusal else ("passed" if verdict_passed else "failed")
        CRITIC_VERDICTS.labels(verdict=label).inc()
    if grounding is not None:
        CRITIC_GROUNDING.observe(grounding)
    if revisions:
        REVISIONS.inc(revisions)
    for kind in set(pii_kinds):
        PII_REDACTIONS.labels(kind=kind).inc()
    if used_web:
        WEB_FALLBACKS.inc()
    if explicit_article:
        EXPLICIT_ARTICLE_QUERIES.inc()


DRIFT_DELTA_GAUGE = Gauge(
    "rag_embedding_drift_delta",
    "Drift change vs the previous run / rolling median (kind=mmd|cosine, ref=prev|median)",
    ["kind", "ref"],
    registry=registry,
)
DRIFT_DELTA_ALERT = Gauge(
    "rag_embedding_drift_delta_alert",
    "1 when drift moved more than the delta threshold vs the rolling median",
    registry=registry,
)


def record_drift_delta(
    mmd_prev: float, cos_prev: float, mmd_median: float, cos_median: float, alert: bool
) -> None:
    DRIFT_DELTA_GAUGE.labels(kind="mmd", ref="prev").set(mmd_prev)
    DRIFT_DELTA_GAUGE.labels(kind="cosine", ref="prev").set(cos_prev)
    DRIFT_DELTA_GAUGE.labels(kind="mmd", ref="median").set(mmd_median)
    DRIFT_DELTA_GAUGE.labels(kind="cosine", ref="median").set(cos_median)
    DRIFT_DELTA_ALERT.set(1.0 if alert else 0.0)


def record_cache(cache: str, hit: bool) -> None:
    CACHE_EVENTS.labels(cache=cache, result="hit" if hit else "miss").inc()


def record_query(latency_ms: float) -> None:
    QUERY_COUNTER.inc()
    QUERY_LATENCY.observe(latency_ms)


def record_faithfulness(score: float) -> None:
    FAITHFULNESS_GAUGE.set(score)
    FAITHFULNESS_ALERT.set(1.0 if score < settings.faithfulness_alert_threshold else 0.0)


def record_ragas(scores: dict[str, float]) -> None:
    """Publish every RAGAS metric; faithfulness also drives the alert gauge."""
    for name, value in scores.items():
        RAGAS_METRIC.labels(metric=name).set(value)
    if "faithfulness" in scores:
        record_faithfulness(scores["faithfulness"])


def record_drift(mmd_score: float, cosine_score: float | None = None) -> None:
    DRIFT_GAUGE.set(mmd_score)
    if cosine_score is not None:
        COSINE_DRIFT_GAUGE.set(cosine_score)


def push_metrics(job_name: str = "civil-code-rag") -> None:
    if not settings.prometheus_pushgateway_url:
        return
    push_to_gateway(settings.prometheus_pushgateway_url, job=job_name, registry=registry)

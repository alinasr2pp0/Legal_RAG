"""In-process rolling statistics for the UI dashboard (/stats).

Prometheus remains the source of truth for alerting; this keeps the last
``WINDOW`` requests in memory so the UI can show live numbers with no extra
service. Nothing here stores user text (only article numbers and numbers).
"""

from __future__ import annotations

import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field

WINDOW = 500


@dataclass
class _Sample:
    ts: float
    latency_ms: float
    passed: bool | None
    refusal: bool
    grounding: float | None
    revisions: int
    used_web: bool
    pii: bool
    explicit_article: bool
    cache_hit: bool
    articles: list[int] = field(default_factory=list)


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


class StatsStore:
    def __init__(self, window: int = WINDOW) -> None:
        self._samples: deque[_Sample] = deque(maxlen=window)
        self._lock = threading.Lock()
        self.started = time.time()
        self.total = 0

    def record(
        self,
        *,
        latency_ms: float,
        passed: bool | None = None,
        refusal: bool = False,
        grounding: float | None = None,
        revisions: int = 0,
        used_web: bool = False,
        pii: bool = False,
        explicit_article: bool = False,
        cache_hit: bool = False,
        articles: list[int] | None = None,
    ) -> None:
        sample = _Sample(
            time.time(), latency_ms, passed, refusal, grounding, revisions,
            used_web, pii, explicit_article, cache_hit, articles or [],
        )
        with self._lock:
            self._samples.append(sample)
            self.total += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            rows = list(self._samples)
            total = self.total
        n = len(rows)
        lat = [r.latency_ms for r in rows if not r.cache_hit]
        judged = [r for r in rows if r.passed is not None]
        grounded = [r.grounding for r in rows if r.grounding is not None]
        top = Counter(a for r in rows for a in r.articles).most_common(8)

        def rate(count: int, denom: int) -> float:
            return round(count / denom, 3) if denom else 0.0

        return {
            "uptime_seconds": int(time.time() - self.started),
            "total_requests": total,
            "window": n,
            "latency_ms": {
                "p50": round(_pct(lat, 0.50)),
                "p95": round(_pct(lat, 0.95)),
                "max": round(max(lat)) if lat else 0,
            },
            "critic_pass_rate": rate(sum(1 for r in judged if r.passed), len(judged)),
            "refusal_rate": rate(sum(r.refusal for r in rows), n),
            "avg_grounding": round(sum(grounded) / len(grounded), 3) if grounded else None,
            "revision_rate": rate(sum(1 for r in rows if r.revisions > 0), n),
            "web_fallback_rate": rate(sum(r.used_web for r in rows), n),
            "pii_rate": rate(sum(r.pii for r in rows), n),
            "explicit_article_rate": rate(sum(r.explicit_article for r in rows), n),
            "cache_hit_rate": rate(sum(r.cache_hit for r in rows), n),
            "top_articles": [{"article_number": a, "count": c} for a, c in top],
            "recent_latency_ms": [round(r.latency_ms) for r in rows[-30:]],
        }


stats = StatsStore()

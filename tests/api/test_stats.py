from fastapi.testclient import TestClient

from api import main
from rag.monitoring.stats import StatsStore


def test_snapshot_math():
    st = StatsStore()
    for i, ok in enumerate([True, True, False, True]):
        st.record(latency_ms=100 * (i + 1), passed=ok, grounding=0.9, articles=[163, 164])
    st.record(latency_ms=5, cache_hit=True, articles=[163])
    snap = st.snapshot()
    assert snap["total_requests"] == 5 and snap["window"] == 5
    assert snap["critic_pass_rate"] == 0.75 and snap["cache_hit_rate"] == 0.2
    assert snap["top_articles"][0] == {"article_number": 163, "count": 5}
    assert snap["latency_ms"]["p50"] in (200, 300)  # cache hits excluded


def test_window_is_bounded():
    st = StatsStore(window=3)
    for _ in range(10):
        st.record(latency_ms=1)
    assert st.snapshot()["window"] == 3 and st.snapshot()["total_requests"] == 10


def test_stats_endpoint_needs_no_pipeline():
    main._pipeline.clear()
    body = TestClient(main.app).get("/stats").json()
    assert body["corpus"]["articles"] > 1000 and body["system"]["pipeline_loaded"] is False
    assert "p95" in body["latency_ms"]


def test_search_and_feedback(tmp_path, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "feedback_log_path", str(tmp_path / "fb.jsonl"))
    c = TestClient(main.app)
    hits = c.get("/search", params={"q": "التعويض عن العمل غير المشروع"}).json()
    assert hits and all({"article_number", "snippet", "is_repealed"} <= set(h) for h in hits)
    assert c.get("/search", params={"q": ""}).status_code == 422
    r = c.post("/feedback", json={"rating": "down", "question": "رقمي 01012345678",
                                  "comment": "ناقص", "articles": [163]})
    assert r.status_code == 204
    assert c.post("/feedback", json={"rating": "meh"}).status_code == 422
    c.post("/feedback", json={"rating": "up"})
    saved = (tmp_path / "fb.jsonl").read_text(encoding="utf-8")
    assert "01012345678" not in saved and "[phone]" in saved
    assert c.get("/stats").json()["feedback"] == {"up": 1, "down": 1, "positive_rate": 0.5}

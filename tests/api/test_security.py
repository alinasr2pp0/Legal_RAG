"""Security / isolation regressions: LOCAL_ONLY really blocks external sockets at runtime,
URL-spoofing tricks do not pass the locality check, PII never reaches cache or logs,
unverified answers are not cached."""
import socket

import pytest
from fastapi.testclient import TestClient

from api import main
from core.local_only import is_local_url
from tests.api.test_end_to_end_local import CHUNKS, orchestrator  # noqa: F401

needs_corpus = pytest.mark.skipif(not CHUNKS.exists(), reason="serving bundle not exported")


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost.evil.com/v1",
        "http://localhost@evil.com/v1",
        "https://qdrant.evil.com",
        "http://8.8.8.8:11434/v1",
        "https://api.openai.com/v1",
        "http://evil.com#localhost",
        "",
    ],
)
def test_spoofed_urls_are_not_local(url):
    assert not is_local_url(url)


@pytest.mark.parametrize(
    "url",
    ["http://localhost:11434/v1", "http://host.docker.internal:11434/v1",
     "http://127.0.0.1:6333", "http://192.168.1.20:11434", "http://qdrant:6333"],
)
def test_genuinely_local_urls(url):
    assert is_local_url(url)


@needs_corpus
def test_full_pipeline_opens_no_non_local_socket(orchestrator, monkeypatch):  # noqa: F811
    attempts: list[object] = []
    real_connect = socket.socket.connect

    def guard(self, address):  # type: ignore[no-untyped-def]
        host = address[0] if isinstance(address, tuple) else str(address)
        if not is_local_url(str(host)):
            attempts.append(address)
            raise OSError("blocked by test: non-local connection")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(main.settings, "local_only", True)
    main._pipeline.clear()
    main._pipeline.update(orchestrator=orchestrator)
    main._answer_cache.clear()
    r = TestClient(main.app).post("/ask", json={"question": "ما نص المادة 163؟"})
    main._pipeline.clear()
    assert r.status_code == 200 and attempts == []


@needs_corpus
def test_pii_question_is_redacted_and_never_cached_or_logged(orchestrator, monkeypatch):  # noqa: F811
    logged: list[str] = []
    monkeypatch.setattr(main, "log_query", lambda q, p: logged.append(q))
    main._pipeline.clear()
    main._pipeline.update(orchestrator=orchestrator)
    main._answer_cache.clear()
    client = TestClient(main.app)
    r = client.post("/ask", json={"question": "رقمي 01012345678 ما نص المادة 164؟"})
    main._pipeline.clear()
    assert r.status_code == 200
    assert "01012345678" not in r.text
    assert all("01012345678" not in q for q in logged)
    assert len(main._answer_cache._data) == 0  # PII question: not stored


@needs_corpus
def test_unverified_answer_is_not_cached(orchestrator, monkeypatch):  # noqa: F811
    from rag.validation.critic import Verdict

    monkeypatch.setattr(
        orchestrator.critic, "run", lambda d, e: Verdict(False, 0.1, ["low_grounding"])
    )
    main._pipeline.clear()
    main._pipeline.update(orchestrator=orchestrator)
    main._answer_cache.clear()
    r = TestClient(main.app).post("/ask", json={"question": "ما نص المادة 165؟"})
    main._pipeline.clear()
    assert r.status_code == 200 and r.json()["critic"]["passed"] is False
    assert len(main._answer_cache._data) == 0


def test_readiness_reports_unreachable_llm_and_missing_model(monkeypatch):
    import httpx

    monkeypatch.setattr(main.settings, "llm_base_url", "http://127.0.0.1:9/v1")
    assert "unreachable" in main._llm_problems()[0]

    class R:
        def raise_for_status(self): ...
        def json(self): return {"data": [{"id": "other-model"}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: R())
    assert "not served" in main._llm_problems()[0]
    monkeypatch.setattr(main.settings, "llm_model_primary", "other-model")
    assert main._llm_problems() == []
    monkeypatch.setattr(main.settings, "llm_model_primary", "qwen2.5:3b")

    class EmptyModels(R):
        def json(self):
            return {"data": []}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: EmptyModels())
    assert "not served" in main._llm_problems()[0]


def test_ready_does_not_enable_chat_when_llm_is_unavailable(monkeypatch):
    monkeypatch.setattr(main, "_pipeline", {})
    monkeypatch.setattr(main, "_llm_problems", lambda: ["LLM server unreachable"])
    monkeypatch.setattr(
        main,
        "_get_pipeline",
        lambda: pytest.fail("pipeline must not load while Ollama is unavailable"),
    )

    response = TestClient(main.app).get("/ready")

    assert response.status_code == 503
    assert "LLM server unreachable" in response.json()["detail"]


def test_langfuse_trace_gets_redacted_question_and_skips_case_answers(monkeypatch):
    from contextlib import nullcontext

    seen: list[tuple[str, bool]] = []

    def fake_trace(q, enabled=True, **kw):
        seen.append((q, enabled))
        return nullcontext((NoopSpans(), "cid"))

    class NoopSpans:
        def span(self, *a, **k):
            return nullcontext()

        def log_generation(self, **k): ...

    from unittest.mock import MagicMock

    from agents.orchestrator import OrchestratorResult

    orch = MagicMock()
    orch.run.return_value = OrchestratorResult("q", "a", [], None)
    monkeypatch.setattr(main, "trace_ask_request", fake_trace)
    main._pipeline.clear()
    main._pipeline.update(orchestrator=orch)
    main._answer_cache.clear()
    TestClient(main.app).post("/ask", json={"question": "رقمي 01012345678 ما نص المادة 163؟"})
    main._pipeline.clear()
    assert seen and "01012345678" not in seen[0][0] and seen[0][1] is True

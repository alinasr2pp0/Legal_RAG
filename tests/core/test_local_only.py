from core.config import Settings, settings
from core.local_only import is_local_url, local_only_violations


def test_is_local_url():
    for u in ["http://localhost:11434/v1", "http://127.0.0.1:6333", "http://ollama:11434",
              "http://host.docker.internal:11434", "http://192.168.1.5:8000"]:
        assert is_local_url(u), u
    for u in ["https://api.openai.com/v1", "https://openrouter.ai/api/v1", "https://cloud.langfuse.com"]:
        assert not is_local_url(u), u


def test_violations_flag_hosted_llm():
    cfg = Settings(local_only=True,
                   llm_base_url="https://openrouter.ai/api/v1")
    assert local_only_violations(cfg)


def test_no_violations_for_local_stack():
    cfg = Settings(local_only=True,
                   llm_base_url="http://localhost:11434/v1",
                   web_search_enabled=False, reranker_enabled=False)
    assert local_only_violations(cfg) == []


def test_langfuse_is_disabled_in_local_only_mode(monkeypatch):
    from rag.monitoring import tracing

    monkeypatch.setattr(settings, "local_only", True)
    monkeypatch.setattr(settings, "langfuse_public_key", "pk")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk")
    monkeypatch.setattr(tracing, "_client", None)

    assert tracing.get_langfuse_client() is None

import pytest

from core.config import Settings, apply_profile


@pytest.fixture(autouse=True)
def _isolate_profile_environment(monkeypatch):
    for name in (
        "PROVIDER_PROFILE",
        "LOCAL_EMBEDDING_MODEL",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIMENSION",
        "LOCAL_ONLY",
        "WEB_SEARCH_ENABLED",
        "RERANKER_ENABLED",
        "LLM_BASE_URL",
        "LLM_MODEL_PRIMARY",
        "LLM_MODEL_FALLBACKS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_profile_fills_unset_values():
    cfg = apply_profile(Settings(_env_file=None, provider_profile="local"))
    assert cfg.local_embedding_model == "intfloat/multilingual-e5-small"
    assert cfg.reranker_enabled is False and cfg.local_only is True
    assert cfg.llm_model_fallbacks == [] and cfg.web_search_enabled is False
    hybrid = apply_profile(Settings(_env_file=None, provider_profile="hybrid_api"))
    assert hybrid.reranker_enabled is True and hybrid.local_only is False


def test_explicit_setting_beats_profile():
    cfg = apply_profile(
        Settings(
            _env_file=None,
            provider_profile="local",
            local_embedding_model="D:/AI-Models/multilingual-e5-small",
            local_only=False,
            reranker_enabled=True,
        )
    )
    assert cfg.local_embedding_model == "D:/AI-Models/multilingual-e5-small"
    assert cfg.reranker_enabled is True and cfg.local_only is False


def test_unknown_profile_is_a_clear_error():
    with pytest.raises(RuntimeError, match="Unknown PROVIDER_PROFILE"):
        apply_profile(Settings(_env_file=None, provider_profile="nope"))


def test_every_profile_key_is_a_real_setting():
    import yaml

    data = yaml.safe_load(open("config/providers.yaml", encoding="utf-8"))
    for name in data["profiles"]:
        apply_profile(Settings(_env_file=None, provider_profile=name))

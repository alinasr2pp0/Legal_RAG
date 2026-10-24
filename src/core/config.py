"""Centralized settings. Values are read from environment variables /
a local .env file (see .env.example)."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    # --- Logging configuration (used by src.core.logging_config) ---
    # LOG_LEVEL (e.g. INFO, DEBUG). Defaults to INFO.
    log_level: str = "INFO"
    # LOG_JSON=true enables JSON-lines output.
    log_json: bool = False
    # LOG_FILE path for a rotating file handler. Empty disables file logging.
    log_file: str = ""


    # --- Embeddings (local sentence-transformers) + vector store (Qdrant) ---
    embedding_dimension: int = 384  # read from the model at startup; kept for the index schema
    # env: LOCAL_EMBEDDING_MODEL or EMBEDDING_MODEL (e.g. intfloat/multilingual-e5-small)
    local_embedding_model: str = Field(
        "intfloat/multilingual-e5-small",
        validation_alias=AliasChoices(
            "local_embedding_model", "LOCAL_EMBEDDING_MODEL", "EMBEDDING_MODEL"
        ),
    )
    local_embedding_batch_size: int = 8
    # None = auto (model name contains "e5"); true/false for a local folder named differently
    embedding_e5_prefixes: bool | None = None
    qdrant_path: str = ""  # embedded mode disabled
    qdrant_url: str = "http://localhost:6333"  # use external Qdrant server
    qdrant_collection: str = "civil_code"

    # --- LLM ---
    # Any OpenAI-compatible server; this project uses Ollama.
    llm_api_key: str = Field(
        "ollama", validation_alias=AliasChoices("llm_api_key", "LLM_API_KEY")
    )
    llm_base_url: str = Field(
        "http://localhost:11434/v1",
        validation_alias=AliasChoices("llm_base_url", "LLM_BASE_URL"),
    )
    llm_model_primary: str = "qwen2.5:3b"  # tag as shown by `ollama list`
    llm_model_fallbacks: list[str] = []  # other Ollama tags to try if the primary fails

    # --- Reranker ---
    reranker_enabled: bool = True  # False -> keep fused order (saves RAM on small machines)
    reranker_required: bool = False  # True -> fail loudly if the reranker cannot load / respond
    voyage_api_key: str = ""  # your own key, only in .env / GitHub Secrets -- never in code
    voyage_rerank_model: str = "rerank-2.5"  # or rerank-2.5-lite (cheaper / faster)
    voyage_base_url: str = "https://api.voyageai.com/v1"
    voyage_timeout_seconds: float = 15.0

    # --- Offline / local-only guarantees ---
    local_only: bool = False  # True -> refuse ANY non-local service (see core/local_only.py)
    hf_offline: bool = False  # True -> models must already be in models_dir (no HF downloads)
    # Hugging Face cache for the embedding model and the reranker (scripts/data/download_models.py)
    models_dir: str = "./models"

    # --- LLM call limits ---
    llm_timeout_seconds: float = 120.0
    llm_max_tokens: int = 700

    # --- Input guardrails ---
    # origins allowed to call the API from a browser (UI is same-origin when served at "/")
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    max_question_chars: int = 2000
    injection_guard_enabled: bool = True

    # --- Case documents (user uploads; in-memory only, never mixed into the law index) ---
    case_upload_enabled: bool = True
    case_max_file_mb: int = 10
    case_max_docs: int = 10
    case_max_chars: int = 400_000  # extracted text per case
    case_ttl_hours: float = 12.0
    case_top_k: int = 4
    feedback_log_path: str = "data/logs/feedback.jsonl"
    query_log_path: str = "data/logs/queries.jsonl"  # PII-redacted; feeds monitor_drift

    # --- Data ---
    chunks_path: str = "data/serving/chunks.json"  # see scripts/data/export_serving_data.py

    # --- Agents / guardrails ---
    agent_max_revisions: int = 1  # writer<->critic loops after the first draft
    critic_min_grounding: float = 0.6  # min share of answer terms found in contexts

    pii_redaction_enabled: bool = True
    web_search_enabled: bool = False  # Tavily fallback; also needs TAVILY_API_KEY
    tavily_api_key: str = ""
    web_search_min_score: float = 0.0  # fallback when best rerank score is below this
    # Tavily guardrails: only legal sources / legal content may reach the writer
    web_allowed_domains: list[str] = [
        "manshurat.org",   # Egyptian legislation portal
        "laweg.net",       # Egyptian legal portal
        "sccourt.gov.eg",  # Supreme Constitutional Court
        "cc.gov.eg",       # Court of Cassation
        "elaws.gov.eg",    # official legislation database (verify before relying on it)
    ]
    web_min_result_score: float = 0.5  # Tavily relevance score floor
    web_min_legal_terms: int = 2  # distinct legal terms a snippet must contain
    web_max_results: int = 3
    web_max_snippet_chars: int = 800
    faithfulness_alert_threshold: float = 0.80


    # --- Observability ---
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    mlflow_tracking_uri: str = "sqlite:///mlflow.db"  # file-store backend is deprecated in mlflow
    mlflow_experiment_name: str = "civil-code-rag"

    prometheus_pushgateway_url: str = ""

    # --- Caching ---
    cache_enabled: bool = True
    cache_max_entries: int = 1024
    cache_ttl_seconds: float = 3600.0

    # --- Provider profile (config/providers.yaml) ---
    provider_profile: str = ""
    providers_file: str = "config/providers.yaml"

    # --- App ---
    app_env: str = "development"
    top_k_retrieval: int = 20
    top_k_rerank: int = 5


def apply_profile(cfg: Settings) -> Settings:
    """Apply ``config/providers.yaml`` profile values for every setting the user
    did NOT set explicitly (env / .env win over the profile)."""
    if not cfg.provider_profile:
        return cfg
    import yaml

    path = Path(cfg.providers_file)
    if not path.exists():
        raise RuntimeError(f"PROVIDER_PROFILE set but {path} not found")
    profiles = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("profiles", {})
    if cfg.provider_profile not in profiles:
        raise RuntimeError(
            f"Unknown PROVIDER_PROFILE={cfg.provider_profile!r}; available: {sorted(profiles)}"
        )
    for key, value in profiles[cfg.provider_profile].items():
        if key not in Settings.model_fields:
            raise RuntimeError(f"providers.yaml: unknown setting {key!r}")
        if key not in cfg.model_fields_set:
            setattr(cfg, key, value)
    return cfg


settings = apply_profile(Settings())

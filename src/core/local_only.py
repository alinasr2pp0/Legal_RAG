"""LOCAL_ONLY mode: a hard guarantee that nothing leaves the machine.

When ``local_only`` is on, every service the pipeline could call must be local:
embeddings (e5-small), vector store (embedded Qdrant or a local server), the LLM
(Ollama / any OpenAI-compatible server on localhost or a private network),
no Tavily or hosted Langfuse, and no Hugging Face downloads at runtime.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from core.config import Settings

_LOCAL_HOSTNAMES = {"localhost", "host.docker.internal", "ollama", "qdrant", "langfuse"}


def is_local_url(url: str) -> bool:
    """True for loopback, private-network addresses, and local docker service names."""
    host = (urlparse(url if "://" in url else f"//{url}").hostname or "").lower()
    if not host:
        return False
    if host in _LOCAL_HOSTNAMES or host.endswith(".local") or host.endswith(".internal"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def local_only_violations(cfg: Settings) -> list[str]:
    """Reasons the current configuration would talk to something non-local
    (empty list == compliant). Only meaningful when ``cfg.local_only``."""
    if not cfg.local_only:
        return []
    problems: list[str] = []
    if cfg.qdrant_url and not is_local_url(cfg.qdrant_url):
        problems.append(f"QDRANT_URL {cfg.qdrant_url!r} is not a local address")
    if not is_local_url(cfg.llm_base_url):
        problems.append(
            f"LLM_BASE_URL {cfg.llm_base_url!r} is not local "
            "(use Ollama: http://localhost:11434/v1)"
        )
    if cfg.reranker_enabled:
        problems.append("RERANKER_ENABLED must be false (Voyage is an external service)")
    if cfg.web_search_enabled:
        problems.append("WEB_SEARCH_ENABLED must be false (Tavily is an external service)")
    if cfg.prometheus_pushgateway_url and not is_local_url(cfg.prometheus_pushgateway_url):
        problems.append("PROMETHEUS_PUSHGATEWAY_URL is not a local address")
    return problems

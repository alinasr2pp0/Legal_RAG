"""Tool: optional web search through Tavily, behind strict legal-only guardrails.

Disabled by default and impossible in ``LOCAL_ONLY`` mode. When enabled it
needs your own ``TAVILY_API_KEY``. A web result only reaches the writer if it
passes ALL of these guardrails (each exists to prevent hallucinated "law"):

1. **Domain allowlist** – Tavily is asked to search only ``web_allowed_domains``
   (legal portals / courts) and results from any other host are dropped again
   client-side (never trust the server-side filter alone).
2. **Relevance floor** – Tavily score >= ``web_min_result_score``.
3. **Legal-content check** – the snippet must contain at least
   ``web_min_legal_terms`` distinct legal terms (مادة، قانون، محكمة، نقض، التزام...).
4. **Civil-law topicality** – if the user asked for a specific article, a snippet
   that cites a *different* article of the Civil Code is dropped.
5. **Bounded and labelled** – snippets are truncated, at most ``web_max_results``
   are kept, they carry ``source=web`` (never a Civil Code article number) and the
   prompt tells the model they are unofficial.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from core.config import settings
from core.models import Chunk, ScoredChunk
from rag.ingestion.legal_arabic_text import normalize

TAVILY_URL = "https://api.tavily.com/search"

# Stems of legal vocabulary; a snippet must hit several distinct ones.
_LEGAL_TERMS = (
    "مادة", "المادة", "قانون", "القانون", "المدني", "محكمة", "المحكمة", "نقض", "حكم",
    "التزام", "الالتزام", "عقد", "العقد", "تعويض", "مسئولية", "المسؤولية", "دعوى", "بطلان",
    "تقادم", "ملكية", "حق", "الحقوق", "الايجار", "المؤجر", "البيع", "الضمان", "الدائن", "المدين",
)
_ARTICLE_REF = re.compile(r"(?:المادة|مادة)\s*(?:رقم\s*)?(\d{1,4})")


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def legal_term_count(text: str) -> int:
    """Number of DISTINCT legal terms present in ``text``."""
    tokens = set(normalize(text).split())
    return sum(1 for term in set(_LEGAL_TERMS) if normalize(term) in tokens)


def domain_allowed(url: str, allowed: list[str]) -> bool:
    host = _host(url)
    return any(host == d or host.endswith("." + d) for d in allowed)


def passes_guardrails(
    item: dict[str, object], requested_articles: list[int] | None = None
) -> bool:
    content = str(item.get("content", "")).strip()
    if not content:
        return False
    if not domain_allowed(str(item.get("url", "")), settings.web_allowed_domains):
        return False
    if float(str(item.get("score", 0) or 0)) < settings.web_min_result_score:
        return False
    if legal_term_count(content) < settings.web_min_legal_terms:
        return False
    if requested_articles:
        cited = {int(n) for n in _ARTICLE_REF.findall(normalize(content))}
        if cited and not cited & set(requested_articles):
            return False  # talks about other articles: not evidence for this question
    return True


class TavilySearchTool:
    name = "tavily_search"
    description = "Legal-only web search fallback (allow-listed sources, unofficial)."

    def __init__(
        self,
        api_key: str | None = None,
        max_results: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = settings.tavily_api_key if api_key is None else api_key
        self.max_results = max_results or settings.web_max_results
        self.client = client or httpx.Client(timeout=15.0)

    @property
    def available(self) -> bool:
        return bool(self.api_key) and settings.web_search_enabled and not settings.local_only

    def __call__(
        self, query: str, requested_articles: list[int] | None = None
    ) -> list[ScoredChunk]:
        if not self.available or not settings.web_allowed_domains:
            return []
        try:
            response = self.client.post(
                TAVILY_URL,
                json={
                    "api_key": self.api_key,
                    "query": f"القانون المدني المصري {query}",
                    "max_results": self.max_results * 3,  # over-fetch: guardrails drop many
                    "search_depth": "basic",
                    "include_domains": settings.web_allowed_domains,
                },
            )
            response.raise_for_status()
            results = response.json().get("results", [])
        except (httpx.HTTPError, ValueError):
            return []  # web search is best-effort; never break /ask

        chunks: list[ScoredChunk] = []
        for item in results:
            if not passes_guardrails(item, requested_articles):
                continue
            text = " ".join(str(item["content"]).split())[: settings.web_max_snippet_chars]
            chunks.append(
                ScoredChunk(
                    chunk=Chunk(
                        chunk_id=f"web_{len(chunks)}",
                        text=text,
                        article_ids=["web"],
                        metadata={"source": "web", "url": str(item.get("url", ""))},
                    ),
                    score=float(item.get("score", 0.0)),
                )
            )
            if len(chunks) >= self.max_results:
                break
        return chunks

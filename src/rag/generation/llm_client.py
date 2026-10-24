"""LLM generation layer over any OpenAI-compatible server (Ollama), with an ordered model fallback
chain. Replaces a self-hosted vLLM deployment to avoid GPU hosting."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Iterator

from openai import OpenAI

from core.config import settings
from core.models import Citation, RagAnswer, ScoredChunk
from rag.context_building.builder import build_user_prompt
from rag.generation.prompts import system_prompt


class BaseLLMClient(ABC):
    @abstractmethod
    def generate(
        self, question: str, contexts: list[ScoredChunk], feedback: str | None = None
    ) -> RagAnswer: ...


class OpenAICompatLLMClient(BaseLLMClient):
    def __init__(
        self,
        primary_model: str | None = None,
        fallback_models: list[str] | None = None,
    ) -> None:
        self.client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_seconds,
        )
        self.models = [primary_model or settings.llm_model_primary] + (
            fallback_models or settings.llm_model_fallbacks
        )

    def generate(
        self, question: str, contexts: list[ScoredChunk], feedback: str | None = None
    ) -> RagAnswer:
        user_prompt = build_user_prompt(question, contexts, feedback)

        start = time.perf_counter()
        last_error: Exception | None = None
        for model in self.models:
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt(contexts)},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=settings.llm_max_tokens,
                )
                answer_text = response.choices[0].message.content or ""
                latency_ms = (time.perf_counter() - start) * 1000
                citations = [
                    Citation(
                        article_id=c.chunk.article_ids[0],
                        article_number=int(c.chunk.metadata.get("number", 0) or 0),
                        snippet=c.chunk.text[:200],
                    )
                    for c in contexts
                    if c.chunk.metadata.get("number")
                ]
                return RagAnswer(
                    question=question,
                    answer=answer_text,
                    citations=citations,
                    contexts=[c.chunk.text for c in contexts],
                    latency_ms=latency_ms,
                )
            except Exception as exc:  # noqa: BLE001 - fallback chain by design
                last_error = exc
                continue

        raise RuntimeError(f"All models in fallback chain failed: {last_error}")

    def generate_stream(self, question: str, contexts: list[ScoredChunk]) -> Iterator[str]:
        """Yield answer tokens as they arrive (Time-To-First-Token matters
        for the handbook's streaming /ask requirement). Falls back through
        the same model chain as generate(); once a model starts streaming
        successfully we commit to it (no mid-stream model switching)."""
        user_prompt = build_user_prompt(question, contexts)

        last_error: Exception | None = None
        for model in self.models:
            try:
                stream = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt(contexts)},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=settings.llm_max_tokens,
                    stream=True,
                )
                for event in stream:
                    delta = event.choices[0].delta.content if event.choices else None
                    if delta:
                        yield delta
                return
            except Exception as exc:  # noqa: BLE001 - fallback chain by design
                last_error = exc
                continue

        raise RuntimeError(f"All models in fallback chain failed: {last_error}")

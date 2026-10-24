"""Langfuse tracing: one trace per /ask request, with retrieve/rerank/
generate as child spans, plus prompt version, model, token counts, and
cost -- per the handbook's LLMOps requirements.

HONESTY NOTE: this is correct, structurally-complete integration code
against the Langfuse Python SDK's documented API, but it has NOT been
exercised against a real Langfuse project (no LANGFUSE_* keys available
in this environment). Treat the first real /ask call after configuring
keys as the actual validation of this file.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from core.config import settings

if TYPE_CHECKING:
    from langfuse import Langfuse

PROMPT_VERSION = "v1"  # bump when _SYSTEM_PROMPT in llm_client.py changes meaningfully

_client: Langfuse | None = None


def get_langfuse_client() -> Langfuse | None:
    global _client
    if (
        settings.local_only
        or not settings.langfuse_public_key
        or not settings.langfuse_secret_key
    ):
        return None
    if _client is None:
        try:
            from langfuse import Langfuse
        except ImportError:  # optional extra: pip install ".[tracing]"
            return None
        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    return _client


@contextmanager
def trace_ask_request(
    question: str, user_id: str | None = None, session_id: str | None = None,
    enabled: bool = True,
) -> Iterator[tuple[Any, str]]:
    """Wraps one /ask request as a Langfuse trace with retrieve/rerank/
    generate spans available via the yielded `spans` dict of callables."""
    client = get_langfuse_client() if enabled else None
    correlation_id = str(uuid.uuid4())

    if client is None:
        # No keys configured -- yield no-op spans so callers don't need
        # to branch on whether tracing is active.
        yield _NoOpSpans(), correlation_id
        return

    trace = client.trace(
        name="ask",
        input={"question": question},
        user_id=user_id,
        session_id=session_id,
        metadata={"correlation_id": correlation_id, "prompt_version": PROMPT_VERSION},
    )
    spans = _LangfuseSpans(trace)
    try:
        yield spans, correlation_id
    finally:
        client.flush()


class _NoOpSpans:
    @contextmanager
    def span(self, name: str, **kwargs: Any) -> Iterator[None]:
        yield None

    def log_generation(self, **kwargs: Any) -> None:
        pass


class _LangfuseSpans:
    def __init__(self, trace: Any) -> None:
        self.trace = trace

    @contextmanager
    def span(self, name: str, **kwargs: Any) -> Iterator[Any]:
        start = time.perf_counter()
        span = self.trace.span(name=name, input=kwargs.get("input"))
        try:
            yield span
        finally:
            span.end(output=kwargs.get("output"))
            span.update(metadata={"latency_ms": (time.perf_counter() - start) * 1000})

    def log_generation(
        self,
        model: str,
        prompt: str,
        completion: str,
        usage: dict[str, int] | None = None,
    ) -> None:
        self.trace.generation(
            name="generate",
            model=model,
            model_parameters={"temperature": 0.1},
            prompt=prompt,
            completion=completion,
            usage=usage,
            metadata={
                "prompt_version": PROMPT_VERSION,
                "retrieval_top_k": settings.top_k_retrieval,
            },
        )

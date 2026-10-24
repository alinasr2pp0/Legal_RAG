"""Tests the LLM fallback chain logic: if model 1 fails, model 2
is tried, etc. Mocks the OpenAI SDK client — no real network calls."""
from unittest.mock import MagicMock, patch

from core.models import Chunk, ScoredChunk


def _scored_chunk(article_number: int, text: str) -> ScoredChunk:
    chunk = Chunk(
        chunk_id=f"article_{article_number}_p0",
        text=text,
        article_ids=[f"article_{article_number}"],
        metadata={"number": article_number},
    )
    return ScoredChunk(chunk=chunk, score=0.9)


@patch("rag.generation.llm_client.OpenAI")
def test_falls_back_to_second_model_on_failure(mock_openai_cls):
    from rag.generation.llm_client import OpenAICompatLLMClient

    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    success_response = MagicMock()
    success_response.choices = [MagicMock(message=MagicMock(content="الإجابة الصحيحة"))]

    # First model call raises, second succeeds.
    mock_client.chat.completions.create.side_effect = [
        RuntimeError("model unavailable"),
        success_response,
    ]

    client = OpenAICompatLLMClient(
        primary_model="model-a", fallback_models=["model-b", "model-c"]
    )
    contexts = [_scored_chunk(163, "نص المادة")]
    result = client.generate("سؤال قانوني", contexts)

    assert result.answer == "الإجابة الصحيحة"
    assert mock_client.chat.completions.create.call_count == 2
    assert result.citations[0].article_number == 163


@patch("rag.generation.llm_client.OpenAI")
def test_raises_when_all_models_fail(mock_openai_cls):
    from rag.generation.llm_client import OpenAICompatLLMClient

    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.side_effect = RuntimeError("down")

    client = OpenAICompatLLMClient(primary_model="a", fallback_models=["b"])
    try:
        client.generate("سؤال", [_scored_chunk(1, "نص")])
        raise AssertionError("should have raised")
    except RuntimeError as e:
        assert "All models in fallback chain failed" in str(e)

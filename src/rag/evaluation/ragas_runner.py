"""Run RAGAS metrics (faithfulness, answer relevancy, context precision,
context recall) against an evaluation dataset, using the configured OpenAI-compatible
LLM (Ollama locally) and the local embedder instead of the OpenAI defaults, and log
results to MLflow."""

from __future__ import annotations

from dataclasses import dataclass

import mlflow
from datasets import Dataset
from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI
from ragas import evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

from core.config import settings


class _LocalLangchainEmbeddings(Embeddings):  # type: ignore[misc]
    """Our own embedder behind LangChain's interface, so RAGAS never calls an external
    embeddings API (answer_relevancy defaults to OpenAI embeddings)."""

    def __init__(self) -> None:
        from rag.indexing.factory import build_embedder

        self._embedder = build_embedder()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embedder.embed_query(text)


@dataclass
class EvalExample:
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str | None = None


class RagasRunner:
    def __init__(self, model: str | None = None) -> None:
        self.llm = LangchainLLMWrapper(
            ChatOpenAI(
                model=model or settings.llm_model_primary,
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                temperature=0,
            )
        )
        self.embeddings = LangchainEmbeddingsWrapper(_LocalLangchainEmbeddings())
        self.metrics = [faithfulness, answer_relevancy, context_precision, context_recall]

    def run(
        self, examples: list[EvalExample], mlflow_run_name: str = "ragas-eval"
    ) -> dict[str, float]:
        dataset = Dataset.from_dict(
            {
                "question": [e.question for e in examples],
                "answer": [e.answer for e in examples],
                "contexts": [e.contexts for e in examples],
                "ground_truth": [e.ground_truth or "" for e in examples],
            }
        )

        result = evaluate(dataset, metrics=self.metrics, llm=self.llm, embeddings=self.embeddings)
        if hasattr(result, "_repr_dict"):
            raw_scores = result._repr_dict
        elif hasattr(result, "items"):
            raw_scores = dict(result.items())
        else:
            raw_scores = dict(result)
        scores = {k: float(v) for k, v in raw_scores.items()}

        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        mlflow.set_experiment(settings.mlflow_experiment_name)
        with mlflow.start_run(run_name=mlflow_run_name):
            mlflow.log_metrics(scores)
            mlflow.log_param("num_examples", len(examples))

        return scores

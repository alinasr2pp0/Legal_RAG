"""Real MLflow experiments comparing chunking strategies on the actual
corpus. Runs entirely locally (file-based MLflow backend) -- no API keys
needed. Logs chunk_size/overlap as params and structural metrics as
results.

Besides the structural metrics it logs the offline BM25 retrieval quality (hit@1 / hit@5 / MRR on
data/eval/golden_set.json) of every chunking strategy, so the strategies can be compared on
retrieval, not just on chunk counts.

NOTE ON SCOPE: RAGAS faithfulness is NOT logged here because it needs the running service and the LLM.
Run scripts/evaluation/run_evaluation.py per strategy to add it (same run_name).

Usage:
    python scripts/evaluation/mlflow_chunking_experiments.py
    mlflow ui --backend-store-uri sqlite:///mlflow.db        # then open http://localhost:5000
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

import mlflow

from core.config import settings
from core.models import Article
from rag.chunking.chunker import ArticleAwareChunker

STRATEGIES = [
    {"name": "article_1200_150", "max_chars": 1200, "overlap_chars": 150},
    {"name": "article_800_100", "max_chars": 800, "overlap_chars": 100},
    {"name": "article_1500_200", "max_chars": 1500, "overlap_chars": 200},
    {"name": "article_600_50", "max_chars": 600, "overlap_chars": 50},
    {"name": "article_2000_0", "max_chars": 2000, "overlap_chars": 0},
]


def _offline_eval():  # type: ignore[no-untyped-def]
    """Reuse evaluate() from eval_retrieval_offline.py (scripts/ is not a package)."""
    path = Path(__file__).with_name("eval_retrieval_offline.py")
    spec = importlib.util.spec_from_file_location("eval_retrieval_offline", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.evaluate


def _articles_path() -> Path:
    """DVC output when you ran `dvc repro`, else the committed copy in data/serving."""
    interim = Path("data/interim/articles_clean.json")
    return interim if interim.exists() else Path("data/serving/articles_clean.json")


def main() -> None:
    with open(_articles_path(), encoding="utf-8") as f:
        articles = [Article(**item) for item in json.load(f)]
    with open("data/eval/golden_set.json", encoding="utf-8") as f:
        golden = json.load(f)
    evaluate = _offline_eval()

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment_name)

    print(f"{'strategy':<20} {'num_chunks':>10} {'avg_len':>8} {'max_len':>8} {'split_articles':>15}"
          f" {'bm25_hit@5':>11}")
    for strategy in STRATEGIES:
        chunker = ArticleAwareChunker(
            max_chars=strategy["max_chars"], overlap_chars=strategy["overlap_chars"]
        )
        chunks = chunker.chunk(articles)

        lengths = [len(c.text) for c in chunks]
        avg_len = sum(lengths) / len(lengths)
        max_len = max(lengths)
        min_len = min(lengths)

        # how many source articles got split into >1 chunk
        from collections import Counter

        per_article = Counter(c.article_ids[0] for c in chunks)
        split_articles = sum(1 for count in per_article.values() if count > 1)

        with mlflow.start_run(run_name=strategy["name"]):
            mlflow.log_param("chunk_size", strategy["max_chars"])
            mlflow.log_param("overlap", strategy["overlap_chars"])
            mlflow.log_param("embedding_model", settings.local_embedding_model)
            mlflow.log_param("num_source_articles", len(articles))

            mlflow.log_metric("num_chunks", len(chunks))
            mlflow.log_metric("avg_chunk_length_chars", avg_len)
            mlflow.log_metric("max_chunk_length_chars", max_len)
            mlflow.log_metric("min_chunk_length_chars", min_len)
            mlflow.log_metric("articles_split_into_multiple_chunks", split_articles)
            quality = evaluate(chunks, golden, "legal")
            for key in ("hit@1", "hit@5", "mrr"):
                mlflow.log_metric("bm25_" + key.replace("@", "_at_"), quality[key])

            with tempfile.TemporaryDirectory() as tmp:  # portable (no hard-coded /tmp on Windows)
                sample_path = Path(tmp) / f"{strategy['name']}_sample.json"
                sample_path.write_text(
                    json.dumps([c.model_dump() for c in chunks[:5]], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                mlflow.log_artifact(str(sample_path))

        print(
            f"{strategy['name']:<20} {len(chunks):>10} {avg_len:>8.0f} "
            f"{max_len:>8} {split_articles:>15} {quality['hit@5']:>11.3f}"
        )

    print("\nAll runs logged. View with: mlflow ui --backend-store-uri", settings.mlflow_tracking_uri)


if __name__ == "__main__":
    import argparse

    argparse.ArgumentParser(description=__doc__).parse_args()  # --help must not run experiments
    main()

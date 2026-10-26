#!/usr/bin/env python
"""Run evaluation of the RAG API and log results to MLflow.

Usage (PowerShell):
    & ".venv\Scripts\python.exe" scripts\run_evaluation.py --dataset data\eval\golden_set_v1.json

The script:
  * reads a JSON list of queries with optional ground‑truth article IDs.
  * calls the FastAPI ``/ask`` endpoint (debug mode) for each query.
  * measures request latency, retrieval size and returns.
  * computes basic IR metrics (Recall@k, MRR) when ground‑truth is present.
  * logs parameters, metrics and a ``results.csv`` artifact to the
    ``Egyptian-Civil-Code-RAG`` MLflow experiment.
"""

import argparse
import csv
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import mlflow
import requests

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def load_dataset(path: Path) -> list[dict[str, Any]]:
    """Load evaluation dataset.

    Expected format:
    [
        {"question": "...", "ground_truth": ["article_id1", "article_id2"]},
        ...
    ]
    """
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def call_api(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST payload to the RAG ``/ask`` endpoint and return JSON response.
    ``debug`` must be true to obtain retrieval metadata.
    """
    start = time.time()
    response = requests.post(url, json=payload, timeout=30)
    latency_ms = (time.time() - start) * 1000
    response.raise_for_status()
    data = response.json()
    data["_latency_ms"] = latency_ms
    return data

def compute_metrics(results: list[dict[str, Any]]) -> dict[str, float]:
    """Compute simple IR metrics from the result list.
    Supports Recall@k (k=1,3,5) and MRR when ``ground_truth`` is provided.
    """
    recall_at = {1: 0, 3: 0, 5: 0}
    mrr = 0.0
    total = 0
    for r in results:
        gt = r.get("ground_truth")
        if not gt:
            continue
        total += 1
        retrieved = r.get("retrieved_ids", [])
        # Recall@k
        for k in recall_at:
            if any(doc in gt for doc in retrieved[:k]):
                recall_at[k] += 1
        # MRR
        rank = next((i for i, doc in enumerate(retrieved, start=1) if doc in gt), None)
        if rank:
            mrr += 1.0 / rank
    if total == 0:
        return {}
    metrics = {f"recall_at_{k}": recall_at[k] / total for k in recall_at}
    metrics["mrr"] = mrr / total
    return metrics

# ---------------------------------------------------------------------------
# Main routine
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="RAG evaluation script")
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Path to evaluation JSON dataset",
    )
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8000/ask",
        help="FastAPI ask endpoint (debug mode will be forced)",
    )
    args = parser.parse_args()

    dataset = load_dataset(args.dataset)
    results: list[dict[str, Any]] = []
    for entry in dataset:
        question = entry["question"]
        payload = {"question": question, "debug": True}
        try:
            resp = call_api(args.api_url, payload)
            # The API returns ``retrieved`` list with ``id`` field per doc.
            retrieved_ids = [doc.get("id") for doc in resp.get("retrieved", [])]
            result = {
                "question": question,
                "answer": resp.get("answer"),
                "retrieved_ids": retrieved_ids,
                "latency_ms": resp.get("_latency_ms"),
                "ground_truth": entry.get("ground_truth"),
            }
            results.append(result)
        except Exception as e:
            results.append({
                "question": question,
                "error": str(e),
                "ground_truth": entry.get("ground_truth"),
            })

    # Write CSV artifact
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    artifact_path = Path("results_" + timestamp + ".csv")
    with artifact_path.open("w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["question", "answer", "latency_ms", "retrieved_ids", "ground_truth", "error"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    # Compute metrics
    metrics = compute_metrics(results)

    # Log to MLflow
    mlflow.set_tracking_uri("sqlite:///mlflow.db")
    mlflow.set_experiment("Egyptian-Civil-Code-RAG")
    with mlflow.start_run():
        mlflow.log_params({"dataset": str(args.dataset), "api_url": args.api_url})
        for k, v in metrics.items():
            mlflow.log_metric(k, v)
        # Log average latency if available
        latencies = [r["latency_ms"] for r in results if "latency_ms" in r]
        if latencies:
            mlflow.log_metric("avg_latency_ms", sum(latencies) / len(latencies))
        mlflow.log_artifact(str(artifact_path))

    print("Evaluation completed. Logged run to MLflow experiment 'Egyptian-Civil-Code-RAG'.")
    print(f"Metrics: {metrics}")

if __name__ == "__main__":
    main()

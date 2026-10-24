"""Scheduled job (run via cron / GitHub Actions schedule) that:
1. Embeds a sample of recent production queries (from a query log file)
2. Compares them against the stored baseline embedding distribution
3. Pushes the drift metrics + latest RAGAS faithfulness to Prometheus

HONESTY NOTE: step 1 needs a real query log, which only exists once /ask
has real production traffic (e.g. captured via Langfuse export). The
baseline embeddings file (data/processed/baseline_embeddings.npy) must
be created once from the initial corpus via scripts/data/build_index.py's
output before this script has anything to compare against.

Usage (intended to run on a schedule, e.g. daily):
    python scripts/evaluation/monitor_drift.py --query-log data/logs/queries.jsonl
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from rag.evaluation.drift import DriftDetector, DriftHistory
from rag.indexing.factory import build_embedder
from rag.ingestion.legal_arabic_text import prepare_for_embedding
from rag.monitoring.exporter import (
    push_metrics,
    record_drift,
    record_drift_delta,
    record_faithfulness,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query-log", required=True, help="JSONL file, one {'question': ...} per line")
    ap.add_argument(
        "--baseline", default="data/processed/baseline_embeddings.npy", help="Stored baseline embeddings"
    )
    ap.add_argument("--latest-ragas-scores", default="data/eval/ragas_scores.json")
    ap.add_argument("--history", default="data/logs/drift_history.jsonl")
    ap.add_argument("--delta-threshold", type=float, default=0.05)
    args = ap.parse_args()

    baseline = np.load(args.baseline)

    embedder = build_embedder()  # same backend + same text preparation as indexing
    with open(args.query_log, encoding="utf-8") as f:
        questions = [json.loads(line)["question"] for line in f if line.strip()]

    if not questions:
        print("No queries in log — nothing to evaluate this run.")
        return

    current_embeddings = np.array([embedder.embed_query(prepare_for_embedding(q)) for q in questions])

    detector = DriftDetector(baseline_embeddings=baseline)
    result = detector.evaluate(current_embeddings)
    print(f"Drift over {len(questions)} recent queries: {result}")
    record_drift(mmd_score=result["mmd"], cosine_score=result["cosine_drift"])
    delta = DriftHistory(args.history, delta_threshold=args.delta_threshold).record(
        float(result["mmd"]), float(result["cosine_drift"])
    )
    record_drift_delta(
        delta.mmd_delta_prev, delta.cosine_delta_prev,
        delta.mmd_delta_median, delta.cosine_delta_median, delta.alert,
    )
    print(f"Drift delta: {delta}")

    try:
        with open(args.latest_ragas_scores, encoding="utf-8") as f:
            ragas_scores = json.load(f)
        record_faithfulness(ragas_scores.get("faithfulness", 0.0))
    except FileNotFoundError:
        print(f"No RAGAS scores found at {args.latest_ragas_scores} yet — skipping faithfulness metric.")

    push_metrics(job_name="civil-code-rag-drift-monitor")
    print("Pushed to Prometheus" if result["alert"] else "No alert threshold breach; pushed to Prometheus")

    if result["alert"]:
        print(f"⚠️  DRIFT ALERT: MMD={result['mmd']:.4f} exceeds threshold")


if __name__ == "__main__":
    main()

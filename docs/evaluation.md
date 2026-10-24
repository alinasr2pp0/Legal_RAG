# Evaluation

| Layer | Command | Needs | Status |
|---|---|---|---|
| Offline retrieval (BM25) | `python scripts/evaluation/eval_retrieval_offline.py` | nothing | measured: hit@5 0.90, MRR 0.79 (60 questions) |
| Unit / integration tests | `pytest` | nothing | 180 tests (coverage ≈88%), e2e over the real corpus with a fake LLM and stub embedder |
| End-to-end citations | `python scripts/evaluation/run_evaluation.py --dataset data/eval/golden_set.json` | running `/ask` (Ollama + index) | **not run yet** |
| RAGAS (faithfulness, relevancy, precision, recall) | add `--ragas` | the local LLM (Ollama) | **not run yet** |
| Chunking experiments | `python scripts/evaluation/mlflow_chunking_experiments.py` | nothing | 5 strategies, each logging structural metrics **and** offline BM25 hit@1/hit@5/MRR. View: `mlflow ui --backend-store-uri sqlite:///mlflow.db`. |
| Drift | `python scripts/evaluation/monitor_drift.py --query-log ...` | embedder + real queries | code + tests only |
| Load | `scripts/loadtest/locustfile.py` | running service | stub-LLM run only (`reports/loadtest_stub.md`, CSVs `reports/locust_*stats.csv`); real run pending. **With Voyage/Tavily on, a real run makes paid external calls per request** — keep `LOCUST_UNIQUE_RATIO` low or run against the stub |
| Golden-set audit | `python scripts/evaluation/audit_golden_set.py` | nothing | 60 questions: 7 tagged leaky/explicit, ground truth refreshed, 0 human-reviewed |
| Retrieval benchmark | `python scripts/evaluation/benchmark_retrieval.py` | models for Dense/Hybrid/Reranker | BM25 measured; others BLOCKED here |

Golden set: 60 questions with the expected article. Written by the assistant from article texts and
**not yet reviewed by a lawyer** (`reviewed_by_human: false`); `ground_truth` is the article text, not a
written reference answer. Treat its numbers as optimistic. See `reports/retrieval_bm25_eval.md` for the
before/after table and its caveats.

Quality gates in CI: coverage ≥ 70%, offline retrieval hit@5 ≥ 0.80.

Full benchmark (BM25 measured; Dense/Hybrid/Reranker BLOCKED without models): `scripts/evaluation/benchmark_retrieval.py` → `reports/retrieval_benchmark.json`. Load test: `reports/loadtest_stub.md` (stub LLM — not production latency). RAGAS and reranker distillation have NOT been run (need the real LLM / models).

# Project structure

```
.
├── src/
│   ├── core/                 config, models, guardrails (PII/injection), caches, local-only checks, logs, case store
│   ├── rag/                  the RAG pipeline, one package per stage, in execution order
│   │   ├── ingestion/        parser, pdf_repair, source_corrections, normalizer, validator, legal_arabic_text, case_extract
│   │   ├── chunking/         chunker (article-aware, 1,150 chunks)
│   │   ├── embedding/        embedder (multilingual-e5-small)
│   │   ├── indexing/         vector_store (Qdrant), manifest (index <-> dataset), factory
│   │   ├── query_processing/ query_analysis (article refs, BM25 tokens, embedding text)
│   │   ├── retrieval/        sparse (BM25), dense (vector store), hybrid (dense + sparse + pinning)
│   │   ├── fusion/           rrf (Reciprocal Rank Fusion)
│   │   ├── reranking/        reranker (Voyage API / pass-through)
│   │   ├── context_building/ builder (labelled evidence block, user prompt)
│   │   ├── generation/       prompts, llm_client (Ollama, OpenAI-compatible)
│   │   ├── validation/       critic (citations, grounding, honest refusal)
│   │   ├── evaluation/       ragas_runner, drift
│   │   └── monitoring/       exporter (Prometheus), stats, tracing (Langfuse)
│   ├── agents/               orchestrator, retriever agent, writer agent
│   ├── tools/                search_documents, tavily_search (optional)
│   └── api/                  main.py (FastAPI app), cases.py
├── Frontend/                 index.html (single-page UI served by the API at /)
├── scripts/
│   ├── data/                 parse_pdf, validate_and_normalize, chunk_articles, build_index, export_serving_data, download_models
│   ├── evaluation/           run_evaluation, eval_retrieval_offline, benchmark_retrieval, audit_golden_set, mlflow_chunking_experiments, monitor_drift
│   ├── loadtest/             locustfile, loadtest_server_stub
│   └── ops/                  check_local_stack
├── tests/                    mirrors src/: core, rag, agents, tools, api, evaluation
├── data/                     raw/ interim/ processed/ (DVC) · serving/ (committed corpus + MANIFEST) · eval/ (golden set)
├── monitoring/               prometheus.yml + alerts.yml · local/ (run without Docker) · grafana/ (dashboards + provisioning)
├── config/providers.yaml     model/backend profiles        params.yaml  chunking/retrieval parameters
├── reports/                  measured results (BM25 benchmark, load test, reranker template)
├── docs/                     architecture, data-quality, deployment, evaluation, operations, this file
└── Dockerfile · docker-compose.yml · dvc.yaml · pyproject.toml · .env.example
```

Run the API: `uvicorn api.main:app --app-dir src --port 8000` (or `pip install -e .` first and drop `--app-dir`).
Top-level packages are `core`, `rag`, `agents`, `tools`, `api`; tests put `src` on `PYTHONPATH` (pyproject).

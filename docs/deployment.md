# Deployment

## Local with Docker (default)
```
cp .env.example .env
docker compose up -d --build
```
Ollama runs natively on the host (install the Windows app, `ollama pull qwen2.5:3b`); containers reach it at `http://host.docker.internal:11434/v1` (if unreachable, set `OLLAMA_HOST=0.0.0.0` on the host and restart Ollama). Services: `api` (UI at :8000), `qdrant`, `prometheus`, `pushgateway`, `grafana`; one-shot
`init-models` (downloads the embedding model + reranker into the `models` volume; the only step allowed
to reach Hugging Face) and `indexer` (embeds
`data/serving/chunks.json` into Qdrant; re-running is an idempotent upsert).

The LLM endpoint is `LLM_BASE_URL` / `LLM_API_KEY`; any non-empty key works for Ollama.
Models are chosen in `.env`: `EMBEDDING_MODEL` (default `intfloat/multilingual-e5-small`, 384-d; E5
`query:`/`passage:` prefixes are added automatically and the vector size is read from the model),
`VOYAGE_RERANK_MODEL` (`rerank-2.5`), `LLM_MODEL_PRIMARY` (Ollama tag). Changing the embedding
model requires re-indexing (`python scripts/data/build_index.py ... --recreate`); a dimension mismatch is
reported with that exact hint.

## Local without Docker
Case uploads support TXT, Markdown, DOCX, and PDFs with a text layer. Image files and scanned PDFs without
extractable text are rejected. Prometheus/Grafana: `monitoring/local/README.md`.
```
pip install -e ".[dev]"
copy .env.example .env
ollama pull qwen2.5:3b
python scripts/data/download_models.py
python scripts/data/build_index.py --input data/serving/chunks.json
uvicorn api.main:app --app-dir src --port 8000
```

## Docker image / CI
`data/serving/chunks.json`, `config/` and `scripts/` are baked in (BM25 needs the corpus at runtime).
Workflows: `ci.yml` (lint, mypy, tests, retrieval quality gate) and `docker.yml` (build; push to Docker
Hub on main; needs the repository secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`). The image build
itself has not been executed in the authoring sandbox. DVC (`dvc.yaml`) is run locally with `dvc repro`.

## When `/ask` answers 503
The message names what is missing (`chunks.json`, a non-local backend under LOCAL_ONLY, an unreachable LLM). `/health` keeps working. `/ready` additionally checks that Ollama is reachable and serves `LLM_MODEL_PRIMARY`, that the Qdrant vector count equals the corpus, and that the index manifest matches the dataset hash, embedding model and dimension.

## Default mode: fully local

`.env.example` selects `PROVIDER_PROFILE=local` and `LOCAL_ONLY=true`; reranking and web search are disabled.
The embedding model, vector index, and Ollama LLM run locally. Optional hosted provider profiles remain
available only when explicitly selected and local-only mode is disabled.

## Fully local mode (no external service)

`PROVIDER_PROFILE=local` (or `local_full`) with `LOCAL_ONLY=true` disables external providers and tracing.
The local profile uses embedded Qdrant, a local embedding model, and Ollama. Setup:

1. `ollama pull qwen2.5:3b`
2. Set `EMBEDDING_MODEL` to an existing local model directory, or download the embedding model once with
   `python scripts/data/download_models.py` before enabling `HF_OFFLINE=true`.
3. `python scripts/data/build_index.py --input data/serving/chunks.json [--recreate]` if the local index is absent or stale.
4. `python scripts/ops/check_local_stack.py` (must print only OK)
5. `uvicorn api.main:app --app-dir src` — `GET /ready` checks the LLM and index.

## Reranker

Voyage Rerank API (`RERANKER_ENABLED=true`, `VOYAGE_RERANK_MODEL`, default `rerank-2.5`). Missing key at startup => fallback to the fused order
unless `RERANKER_REQUIRED=true`. `/ready` and `/stats` show the active reranker.

## Tavily legal-only guardrails (only when LOCAL_ONLY is off)

Results are kept only if: domain is in `WEB_ALLOWED_DOMAINS` (also sent as
`include_domains`), score >= `WEB_MIN_RESULT_SCORE`, snippet has >=
`WEB_MIN_LEGAL_TERMS` distinct legal terms, it does not cite only *other*
articles than the one asked about, and it is truncated/capped and labelled
"unofficial web source". Verify the default domain list before relying on it.

## Request hardening

Question length cap (`MAX_QUESTION_CHARS`), prompt-injection refusal without an LLM
call, LLM timeout/max tokens, PII-redacted query log (`data/logs/queries.jsonl`,
input to `scripts/evaluation/monitor_drift.py`). `/ask/stream` runs the SAME full pipeline as `/ask` (retrieve → write → critic loop); the verified answer is then streamed word-by-word, followed by `event: result` (sources, critic, flags). Streaming starts after verification, so first-token latency equals pipeline latency.

## CI/CD and Docker Hub (GitHub Actions)

* `.github/workflows/ci.yml` — every push / PR to `main`: ruff, mypy, pytest (coverage gate 70%), package build,
  the offline BM25 retrieval gate (hit@5 ≥ 0.80 on `data/serving/chunks.json`) and `scripts/ops/check_monitoring_configs.py`.
  It needs no secrets and runs on a clean checkout (the committed `data/serving/` bundle is enough).
* `.github/workflows/docker.yml` — builds the image on GitHub's runners (no local Docker needed), smoke-tests `/health`
  and the UI, and **pushes to Docker Hub only on `main` when the secrets exist** (PRs never push).
* One-time Docker Hub link: hub.docker.com → Account settings → Personal access tokens → create a token with
  Read & Write → GitHub repo → Settings → Secrets and variables → Actions → add `DOCKERHUB_USERNAME` and
  `DOCKERHUB_TOKEN`. Then `docker compose` (or any server) can pull `<username>/civil-code-rag:latest`.
* Your Voyage / Tavily keys are **runtime** settings for your own `.env`; CI and the image build never need them.
* `.github/dependabot.yml` opens monthly update PRs for actions, the Dockerfile base image and pip.

# Load test (STUB LLM + STUB embedder) -- read the caveats

Tool: Locust 2.46.7, `scripts/loadtest/locustfile.py`, server `scripts/loadtest/loadtest_server_stub.py`
(real FastAPI app, real corpus, BM25 + embedded-Qdrant hybrid retrieval, critic, caches; **hash
embedder and echo LLM**). Sandbox: 2 shared CPUs (Locust and server on the same machine), 60 s runs.

| Run | users | wait | unique-question ratio | requests | failures | req/s | p50 | p95 | p99 |
|---|---|---|---|---|---|---|---|---|---|
| Realistic pacing | 20 | 1-3 s | 0.3 | 593 | 0 | 9.9 | 3 ms | 11 ms | 28 ms |
| Stress | 40 | 0-0.05 s | 1.0 | 15,609 | 0 | 260 | 110 ms | 250 ms | 300 ms |

Server RSS: 150 MB at start -> 164 MB after run 1 -> 239 MB after run 2 (answer/embedding caches
filling; both are size-bounded).

Caveats
* Excludes real LLM generation (seconds on the target laptop) and real embedding/reranker cost, so
  these numbers show the service's own overhead and that it does not error under concurrency -- they
  are **not** production latency or throughput.
* "Unique" questions are drawn from 1,149 article-number templates, so the cache warms during the run.
* Re-run against `docker compose up` with Ollama to get real figures.

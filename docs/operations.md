# Operations: metrics, alerts, drift

Prometheus metrics (`/metrics`): `rag_queries_total`, `rag_query_latency_ms`, `rag_cache_events_total`,
`rag_faithfulness_score`, `rag_faithfulness_alert`, `rag_ragas_metric{metric}`,
`rag_embedding_drift_mmd`, `rag_embedding_drift_cosine`, `rag_embedding_drift_delta{kind,ref}`,
`rag_embedding_drift_delta_alert`, `rag_critic_verdicts_total{verdict}`, `rag_critic_grounding`,
`rag_answer_revisions_total`, `rag_pii_redactions_total{kind}`, `rag_web_fallback_total`,
`rag_explicit_article_queries_total`.

Alerts (`monitoring/alerts.yml`): faithfulness < 0.80 for 5 min; MMD > 0.15 for 10 min; drift **moving**
(delta vs rolling median > 0.05); critic failures > 20% for 15 min; p95 latency > 8 s for 10 min.

Drift: `scripts/evaluation/monitor_drift.py` embeds recent real queries with the same embedder and text preparation
as indexing, compares them with `baseline_embeddings.npy` (MMD, centroid shift, cosine) and also against the
previous runs (`data/logs/drift_history.jsonl`, rolling median of 7). It needs real traffic; with none it
exits without publishing anything.

Grafana: `monitoring/grafana/dashboards/civil_code_rag.json` — 20 panels in 5 sections (overview stats, traffic &
latency, answer quality & safety, RAGAS & drift, cache), a `datasource` variable, thresholds/units, 15 s refresh. It is
**generated** by `python scripts/ops/build_grafana_dashboard.py` (edit the script, not the JSON), and
`python scripts/ops/check_monitoring_configs.py` (also run in CI) validates the YAML, every PromQL expression and that
every metric used is exported. Import it by hand or use the provisioning in `monitoring/grafana/provisioning`
(datasource uid `prometheus`). The latency histogram is in **milliseconds** (buckets 50 ms … 60 s). It has not been
rendered in a real Grafana here — check it once and add a screenshot to the README for the handbook's evidence.


## Feedback loop
`POST /feedback` (👍/👎 من الواجهة) يكتب `data/logs/feedback.jsonl` (السؤال والتعليق بعد حجب PII). نسبة الرضا تظهر في لوحة المتابعة؛ راجع سجلات 👎 دوريًا وأضف أسئلتها الفاشلة إلى `data/eval/golden_set.json` بعد مراجعة بشرية.

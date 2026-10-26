"""DVC stage: end-to-end evaluation of a running /ask service against the golden set.

    python scripts/evaluation/run_evaluation.py --dataset data/eval/golden_set.json \
        --base-url http://localhost:8000 [--ragas] [--limit 50]

For every question it calls POST /ask and records
  * citation_hit      : expected article is among the cited sources
  * citation_precision: share of cited sources that are the expected article
  * critic_pass_rate  : share of answers the critic agent accepted
and (with --ragas, needs the ragas extra + an LLM key) RAGAS faithfulness,
answer relevancy, context precision/recall.  Scores are written to
data/eval/ragas_scores.json (DVC metric), logged to MLflow, and pushed to
Prometheus (rag_ragas_metric / rag_faithfulness_alert) when a Pushgateway is set.
"""
import argparse
import json
from pathlib import Path

import httpx

from core.config import settings
from rag.monitoring.exporter import push_metrics, record_ragas

OUT = Path("data/eval/ragas_scores.json")


def _contexts_for(sources: list[dict], by_article: dict[int, str]) -> list[str]:
    return [by_article[s["article_number"]] for s in sources if s["article_number"] in by_article]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ragas", action="store_true")
    args = ap.parse_args()

    golden = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    if args.limit:
        golden = golden[: args.limit]
    chunks = json.loads(Path(settings.chunks_path).read_text(encoding="utf-8"))
    by_article: dict[int, str] = {}
    for c in chunks:
        by_article.setdefault(int(c["metadata"]["number"]), c["text"])

    rows = []
    with httpx.Client(base_url=args.base_url, timeout=300.0) as client:
        for item in golden:
            r = client.post("/ask", json={"question": item["question"]})
            r.raise_for_status()
            body = r.json()
            cited = [s["article_number"] for s in body["sources"]]
            rows.append({**item, "answer": body["answer"], "cited": cited,
                         "critic": body.get("critic"),
                         "contexts": _contexts_for(body["sources"], by_article)})

    n = len(rows)
    exp = [r["expected_article"] for r in rows]
    scores: dict[str, float] = {
        "num_questions": float(n),
        "citation_hit": sum(e in r["cited"] for e, r in zip(exp, rows, strict=True)) / n,
        "citation_precision": sum(
            (r["cited"].count(e) / len(r["cited"])) if r["cited"] else 0.0
            for e, r in zip(exp, rows, strict=True)
        ) / n,
        "critic_pass_rate": sum(bool(r["critic"] and r["critic"]["passed"]) for r in rows) / n,
    }

    if args.ragas:
        from rag.evaluation.ragas_runner import EvalExample, RagasRunner

        examples = [EvalExample(r["question"], r["answer"], r["contexts"], r["ground_truth"])
                    for r in rows]
        scores.update(RagasRunner().run(examples))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")
    Path("data/eval/last_run_details.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    record_ragas({k: v for k, v in scores.items() if k != "num_questions"})
    push_metrics()
    print(json.dumps(scores, indent=2))


if __name__ == "__main__":
    main()

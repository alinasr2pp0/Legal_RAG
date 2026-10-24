"""Offline retrieval evaluation (no API keys, no network): BM25-only hit@k / MRR
against data/eval/golden_set.json.  Used to *measure* the effect of the PDF
repair + Arabic tokenizer instead of claiming it.

    python scripts/evaluation/eval_retrieval_offline.py --chunks data/serving/chunks.json
    python scripts/evaluation/eval_retrieval_offline.py --chunks old_chunks.json --tokenizer naive
"""
import argparse
import json

from rank_bm25 import BM25Okapi

from core.models import Chunk
from rag.query_processing.query_analysis import bm25_tokens

KS = (1, 3, 5, 10)


def evaluate(chunks: list[Chunk], golden: list[dict], tokenizer: str) -> dict[str, float]:
    tok = (lambda t: t.split()) if tokenizer == "naive" else bm25_tokens
    bm25 = BM25Okapi([tok(c.text) or ["_"] for c in chunks])
    numbers = [int(c.metadata["number"]) for c in chunks]
    hits = {k: 0 for k in KS}
    rr = 0.0
    for item in golden:
        q = item["question"]
        scores = bm25.get_scores(tok(q))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        ranked: list[int] = []
        for i in order:
            if numbers[i] not in ranked:
                ranked.append(numbers[i])
            if len(ranked) >= max(KS):
                break
        exp = item["expected_article"]
        if exp in ranked:
            r = ranked.index(exp) + 1
            rr += 1.0 / r
            for k in KS:
                hits[k] += r <= k
    n = len(golden)
    return {**{f"hit@{k}": hits[k] / n for k in KS}, "mrr": rr / n, "n": float(n)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", default="data/serving/chunks.json")
    ap.add_argument("--golden", default="data/eval/golden_set.json")
    ap.add_argument("--tokenizer", choices=["naive", "legal"], default="legal")
    ap.add_argument("--min-hit5", type=float, default=0.0, help="exit 1 below this (CI gate)")
    ap.add_argument("--output", default="", help="also write the metrics JSON here")
    args = ap.parse_args()
    with open(args.chunks, encoding="utf-8") as f:
        chunks = [Chunk(**c) for c in json.load(f)]
    with open(args.golden, encoding="utf-8") as f:
        golden = json.load(f)
    metrics = evaluate(chunks, golden, args.tokenizer)
    print(json.dumps(metrics, indent=2))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)
    if metrics["hit@5"] < args.min_hit5:
        raise SystemExit(f"hit@5 {metrics['hit@5']:.3f} < required {args.min_hit5}")

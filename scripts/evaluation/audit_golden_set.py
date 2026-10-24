"""Audit the golden set against the current dataset: stale/damaged ground truth, duplicates,
question<->answer leakage (a question that already contains the article number or copies
its text makes retrieval look better than it is), coverage and label provenance.

    python scripts/evaluation/audit_golden_set.py [--golden data/eval/golden_set.json] [--fix-ground-truth]
"""
import argparse
import json
import re
from collections import Counter

from rag.query_processing.query_analysis import bm25_tokens


def _norm(t: str) -> list[str]:
    return [x for x in bm25_tokens(t) if len(x) >= 3]


def audit(golden: list[dict], articles: dict[int, dict]) -> dict:
    findings: list[dict] = []
    qs = Counter(g["question"].strip() for g in golden)
    for i, g in enumerate(golden):
        n, q, gt = g.get("expected_article"), g["question"], g.get("ground_truth", "")
        art = articles.get(n)
        issue = []
        if art is None:
            issue.append("expected_article_not_in_corpus")
        else:
            if art["is_repealed"]:
                issue.append("expected_article_is_repealed")
            if art.get("text_incomplete") or not art["text"].strip():
                issue.append("expected_article_text_incomplete_or_missing")
            a_tok, gt_tok = set(_norm(art["text"])), _norm(gt)
            if gt_tok and sum(t in a_tok for t in gt_tok) / len(gt_tok) < 0.8:
                issue.append("ground_truth_not_found_in_article_text")
            q_tok = _norm(q)
            if q_tok and sum(t in a_tok for t in q_tok) / len(q_tok) > 0.9 and len(q_tok) > 5:
                issue.append("question_copies_article_text_(leakage)")
        if re.search(rf"(?<!\d){n}(?!\d)", q.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))):
            issue.append("question_contains_article_number_(explicit_lookup,_not_semantic)")
        if qs[q.strip()] > 1:
            issue.append("duplicate_question")
        if re.search(r"\(\s*\)|\)\s*\d\s*\(|\(\s*\d\s*\(\s*\)", gt):
            issue.append("ground_truth_has_pdf_artifacts")
        if issue:
            findings.append({"index": i, "expected_article": n, "issues": issue})
    nums = [g["expected_article"] for g in golden]
    return {
        "n": len(golden),
        "distinct_articles": len(set(nums)),
        "human_reviewed": sum(bool(g.get("reviewed_by_human")) for g in golden),
        "with_findings": len(findings),
        "issue_counts": dict(Counter(x for f in findings for x in f["issues"])),
        "findings": findings,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default="data/eval/golden_set.json")
    ap.add_argument("--articles", default="data/interim/articles_clean.json")
    ap.add_argument("--output", default="")
    ap.add_argument("--refresh", action="store_true",
                    help="rewrite ground_truth from the current article text and tag leaky "
                         "questions (labels stay reviewed_by_human=false)")
    args = ap.parse_args()
    golden = json.load(open(args.golden, encoding="utf-8"))
    articles = {a["number"]: a for a in json.load(open(args.articles, encoding="utf-8"))}
    if args.refresh:
        before = audit(golden, articles)
        leaky = {f["index"] for f in before["findings"]
                 if any("leakage" in x or "explicit_lookup" in x for x in f["issues"])}
        for i, g in enumerate(golden):
            a = articles.get(g["expected_article"])
            if a and a["text"].strip() and not a["is_repealed"]:
                g["ground_truth"] = " ".join(a["text"].split())
            g["query_type"] = "explicit_or_leaky" if i in leaky else "semantic"
        json.dump(golden, open(args.golden, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    rep = audit(golden, articles)
    print(json.dumps({k: v for k, v in rep.items() if k != "findings"}, ensure_ascii=False, indent=2))
    for f in rep["findings"][:40]:
        print(f)
    if args.output:
        open(args.output, "w", encoding="utf-8").write(json.dumps(rep, ensure_ascii=False, indent=2))

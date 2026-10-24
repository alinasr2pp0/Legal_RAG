# Offline retrieval evaluation (BM25 only, no API keys)

Measured with `scripts/evaluation/eval_retrieval_offline.py` on `data/eval/golden_set.json`
(60 questions, one expected article each). Dense retrieval / reranker are **not**
part of these numbers — they need the embedding backend and were not run here.

| Corpus + tokenizer | hit@1 | hit@3 | hit@5 | hit@10 | MRR |
|---|---|---|---|---|---|
| Before: parser v1 text, `str.split()` | 0.550 | 0.717 | 0.717 | 0.800 | 0.639 |
| Parser v2 + repair, `str.split()` | 0.550 | 0.717 | 0.767 | 0.833 | 0.645 |
| Parser v2 + repair + `legal_arabic_text` tokenizer (+ lam-alef fold) + chapter header | **0.717** | **0.883** | **0.900** | **0.917** | **0.790** |

What changed between the rows
* **Parser v2** (`rag/ingestion/parser.py`): v1 anchored on the English "Article N" heading and, on pages
  where that heading sits before the Arabic text, attached text to the wrong article. Measured against
  v2, **65 of 1,143 articles (~6%) had wrong, split or truncated text in v1** (e.g. v1 article 204 held the
  text of 203, v1 388 held 387), 6 articles were missing (120, 452, 888, 1022, 1110, 1115) and 13 had empty
  Arabic text. v2 segments by the monotone chain of Arabic "مادة N" markers: 1,149/1,149 articles, 56
  repealed. Article 1022: its Arabic paragraph (1) is absent from the source PDF; paragraphs (2)-(3)
  were relocated from the 1021 block (documented in `data/interim/source_corrections_applied.json`,
  flagged `text_incomplete`, pending lawyer confirmation).
* Chapter titles are now metadata (`chapter`) and prefixed to the chunk text as a contextual header.
* `rag/ingestion/pdf_repair.py` fixes two systematic PDF-extraction defects found by inspection:
  the lam-alef ligature extracted as `ال` ("الالتزام" → "االلتزام", and the negation
  "لا" → "ال") and multi-digit numbers extracted reversed ("المادة 362" is really 263).
* `rag/ingestion/legal_arabic_text.py` (user-supplied) provides normalization, dialect mapping,
  stop-words that never drop negations, light stemming; one change was needed
  (prefix stripping now keeps 3-letter stems, so "العقد" ≡ "عقد").

Re-measured after the data audit (2026-10, same 60 questions, `scripts/evaluation/benchmark_retrieval.py`,
dataset sha256 in `reports/retrieval_benchmark.json`): all 60 hit@1 0.717 / hit@5 0.900 / MRR 0.790;
on the 53 questions that do not leak the article number or copy its text (`query_type: semantic`)
hit@1 0.698 / hit@5 0.906 / MRR 0.781. Dense, hybrid (RRF) and reranker rows are **BLOCKED** in this
environment (no model weights) and are recorded as such in the JSON -- not estimated.

Golden-set audit (`scripts/evaluation/audit_golden_set.py`): 16 ground truths carried PDF paragraph-number
artifacts (refreshed from the repaired article text), 6 questions copy their article's wording and 1
contains the article number; they are tagged `query_type: explicit_or_leaky`. No label has been
reviewed by a human.

Caveats (read before quoting these numbers)
* Two golden labels (203, 387) were corrected after parser v2 exposed that v1 had mis-numbered them.
* The questions were written by the assistant from the first lines of each article, so they
  share vocabulary with the target text — real user questions will score lower. They have
  **not** been reviewed by a lawyer (`reviewed_by_human: false`).
* One expected article per question; a question that is also answered by a neighbouring
  article is counted as a miss.
* Not run here: e5-small dense retrieval, the cross-encoder reranker, any LLM call, RAGAS.

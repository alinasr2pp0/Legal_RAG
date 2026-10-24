"""Generate a reproducible random-sample checklist for human review of the corpus.

Samples non-repealed articles with a fixed seed so every run yields the same table.
Nothing is pre-approved: a person must compare Arabic and English against the PDF pages.

    python scripts/data/make_review_checklist.py --output docs/corpus-review-checklist.md
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = 20261018
SAMPLE = 20


def build(articles: list[dict], manifest: dict, seed: int, n: int) -> str:
    pool = [a for a in articles if not a["is_repealed"] and a.get("text_en")]
    picked = sorted(random.Random(seed).sample(pool, n), key=lambda a: int(a["number"]))
    rows = "\n".join(
        f"| {a['number']} | {a.get('page_number', '?')} | [ ] | [ ] | |" for a in picked
    )
    missing = manifest.get("text_missing_articles") or []
    incomplete = manifest.get("text_incomplete_articles") or []
    return f"""# Corpus Visual Review Checklist

Status: **pending human review.** The table is a reproducible random sample (seed `{seed}`) of
{n} non-repealed articles. Nothing is pre-approved: compare the Arabic and English text against
the indicated PDF pages (including continuation pages).

Source PDF SHA-256: `{manifest.get("source_pdf_sha256")}`.
Regenerate: `python scripts/data/make_review_checklist.py`.

| Article | PDF page | Text and boundaries | Hierarchy / citation | Reviewer notes |
|---|---|---|---|---|
{rows}

## Additional checks

- [ ] Articles flagged `text_missing`: {missing or "none"} are refused by the service; confirm against the PDF.
- [ ] Articles flagged `text_incomplete`: {incomplete or "none"}; fill the missing Arabic paragraph from an
      official edition. Do not move adjacent text without legal review (see `docs/data-quality.md`).
- [ ] Article 1021/1022 relocation (`data/interim/source_corrections_applied.json`) confirmed by a lawyer.
- [ ] Spot-check restored Arabic numerals and lam-alef words (for example "إسلام") against the PDF.
- [ ] Repealed ranges match the PDF's explicit repeal notes.
- [ ] Approve a corpus version (record the `chunks_sha256` from `data/serving/MANIFEST.json`) before indexing.

Reviewer: ______  Date: ______  Decision: ______
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--articles", default=str(ROOT / "data/interim/articles_clean.json"))
    ap.add_argument("--manifest", default=str(ROOT / "data/serving/MANIFEST.json"))
    ap.add_argument("--output", default=str(ROOT / "docs/corpus-review-checklist.md"))
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--n", type=int, default=SAMPLE)
    args = ap.parse_args()
    articles = json.loads(Path(args.articles).read_text(encoding="utf-8"))
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    out = Path(args.output)
    out.write_text(build(articles, manifest, args.seed, args.n), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

"""DVC stage: validate + normalize raw articles.
Usage: python scripts/data/validate_and_normalize.py --input ... --output ...
"""
import argparse
import json
from dataclasses import asdict

from core.models import Article
from rag.ingestion.normalizer import ArabicNormalizer
from rag.ingestion.pdf_repair import repair_arabic_text
from rag.ingestion.source_corrections import apply_source_corrections
from rag.ingestion.validator import ArticleValidator

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    with open(args.input, encoding="utf-8") as f:
        raw = json.load(f)
    articles = [Article(**item) for item in raw]

    normalizer = ArabicNormalizer()
    for article in articles:
        # 1) repair PDF extraction artifacts (lam-alef order, reversed digits)
        # 2) light normalization (diacritics, tatweel, digits, whitespace)
        if article.text.startswith("[ملغاة]"):  # generated placeholder: already correct
            article.text = normalizer.light(article.text)
        else:
            article.text = normalizer.light(repair_arabic_text(article.text))

    for article in articles:
        for field in ("chapter", "part", "book"):
            value = getattr(article, field)
            if value:
                setattr(article, field, normalizer.light(repair_arabic_text(value, fix_numbers=False)))

    applied = apply_source_corrections(articles)
    with open("data/interim/source_corrections_applied.json", "w", encoding="utf-8") as f:
        json.dump(applied, f, ensure_ascii=False, indent=2)

    report = ArticleValidator().validate(articles)
    with open("data/interim/validation_report.json", "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, ensure_ascii=False, indent=2)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump([a.model_dump() for a in articles], f, ensure_ascii=False, indent=2)

    print(f"Valid: {report.valid}/{report.total} | duplicates: {report.duplicate_numbers} | missing: {report.missing_numbers}")

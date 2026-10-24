"""DVC stage: PDF -> raw structured articles JSON.
Usage: python scripts/data/parse_pdf.py --input data/raw/civil_code.pdf --output data/interim/articles_raw.json
"""
import argparse
import json

from rag.ingestion.parser import CivilCodePdfParser

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    articles = CivilCodePdfParser().parse(args.input)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump([a.model_dump() for a in articles], f, ensure_ascii=False, indent=2)
    print(f"Parsed {len(articles)} articles -> {args.output}")

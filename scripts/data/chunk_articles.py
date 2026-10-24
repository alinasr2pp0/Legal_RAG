"""DVC stage: chunk validated articles.
Usage: python scripts/data/chunk_articles.py --input ... --output ...
"""
import argparse
import json

import yaml

from core.models import Article
from rag.chunking.chunker import ArticleAwareChunker

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    with open("params.yaml", encoding="utf-8") as f:
        params = yaml.safe_load(f)["chunking"]

    with open(args.input, encoding="utf-8") as f:
        articles = [Article(**item) for item in json.load(f)]

    chunker = ArticleAwareChunker(
        max_chars=params["max_chars"], overlap_chars=params["overlap_chars"]
    )
    chunks = chunker.chunk(articles)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump([c.model_dump() for c in chunks], f, ensure_ascii=False, indent=2)
    print(f"Produced {len(chunks)} chunks -> {args.output}")

"""DVC stage: embed chunks and upsert into the vector store (Qdrant).
Usage: python scripts/data/build_index.py --input data/processed/chunks.json
"""

import sys
import argparse
from pathlib import Path
# Ensure src is on the Python path for imports
project_root = Path(__file__).resolve().parents[2]
src_path = project_root / 'src'
sys.path.append(str(src_path))

import numpy as np
import json

from core.models import Chunk
from rag.indexing.factory import build_embedder, build_vector_store, missing_requirements
from rag.ingestion.legal_arabic_text import prepare_for_embedding

BATCH_SIZE = 100
# How many embeddings to keep as the drift baseline (scripts/evaluation/monitor_drift.py
# compares future query embeddings against this distribution).
BASELINE_SAMPLE_SIZE = 500


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--recreate", action="store_true", help="drop the Qdrant collection first")
    ap.add_argument("--include-extra", action="store_true", help="include extra_chunks from rag.extra_texts")
    args = ap.parse_args(argv)

    with open(args.input, encoding="utf-8") as f:
        chunks = [Chunk(**item) for item in json.load(f)]
    # Include any extra Arabic legal texts defined in rag.extra_texts only when requested
    if args.include_extra:
        try:
            from rag.extra_texts import extra_chunks
            chunks.extend(extra_chunks())
        except Exception:
            pass

    problems = missing_requirements()
    if problems:
        raise SystemExit("Missing configuration: " + "; ".join(problems))
    embedder = build_embedder()
    store = build_vector_store()
    if args.recreate and hasattr(store, "recreate"):
        store.recreate()

    baseline_vectors: list[list[float]] = []
    # Determine whether we need to (re)populate the vector store.
    # If the collection already contains points we assume the index was built
    # previously and skip the upsert step to make the script idempotent.
    first_run = store.count() == 0
    if not first_run:
        print("Index already built, skipping upsert.")
        return
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        vectors = embedder.embed_documents([prepare_for_embedding(c.text) for c in batch])
        store.upsert(batch, vectors)
        if len(baseline_vectors) < BASELINE_SAMPLE_SIZE:
            baseline_vectors.extend(vectors)
        print(f"Upserted {i + len(batch)}/{len(chunks)}")

    out_dir = Path("data/processed")
    out_dir.mkdir(parents=True, exist_ok=True)  # absent in the Docker image
    np.save(
        out_dir / "baseline_embeddings.npy",
        np.array(baseline_vectors[:BASELINE_SAMPLE_SIZE]),
    )

    from rag.indexing.manifest import write_index_manifest

    write_index_manifest(
        args.input,
        embedder=type(embedder).__name__,
        model=getattr(embedder, "model_name", ""),
        dimension=len(baseline_vectors[0]) if baseline_vectors else 0,
        num_chunks=len(chunks),
        index_name=store.index_name,
    )
    print(f"Saved drift baseline ({len(baseline_vectors[:BASELINE_SAMPLE_SIZE])} vectors)")


if __name__ == "__main__":
    main()

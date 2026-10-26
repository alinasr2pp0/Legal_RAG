# ruff: noqa: E402
import json
import sys
from pathlib import Path

# Ensure src is on the path
project_root = Path(__file__).resolve().parents[2]
src_path = project_root / 'src'
sys.path.append(str(src_path))

from core.models import Chunk
from rag.indexing.factory import build_embedder, build_vector_store, missing_requirements
from rag.ingestion.legal_arabic_text import prepare_for_embedding


def main():
    # Load existing chunks
    chunks_path = project_root / 'data' / 'processed' / 'chunks.json'
    with open(chunks_path, encoding='utf-8') as f:
        chunks = [Chunk(**item) for item in json.load(f)]

    # Load extra chunks
    try:
        from rag.extra_texts import extra_chunks
        chunks.extend(extra_chunks())
    except Exception as e:
        print('Failed to load extra_chunks:', e)

    problems = missing_requirements()
    if problems:
        raise SystemExit('Missing configuration: ' + '; '.join(problems))

    embedder = build_embedder()
    store = build_vector_store()

    # Recreate collection for a clean index
    if hasattr(store, 'recreate'):
        store.recreate()

    batch_size = 100
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        vectors = embedder.embed_documents([prepare_for_embedding(c.text) for c in batch])
        store.upsert(batch, vectors)
        print(f'Upserted {i + len(batch)}/{len(chunks)}')

if __name__ == '__main__':
    main()

"""scripts/data/build_index.py end to end on a corpus slice with an embedded Qdrant and a hashing
embedder; runs from an empty cwd to catch the Docker case (no data/processed/ directory)."""
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from rag.embedding.embedder import BaseEmbedder
from rag.indexing.vector_store import QdrantVectorStore

CHUNKS = Path(__file__).resolve().parents[2] / "data/serving/chunks.json"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts/data/build_index.py"
DIM = 64


class _Hash(BaseEmbedder):
    def _v(self, t: str) -> list[float]:
        v = [0.0] * DIM
        for tok in t.split():
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM] += 1.0
        n = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts):
        return [self._v(t) for t in texts]

    def embed_query(self, text):
        return self._v(text)


@pytest.mark.skipif(not CHUNKS.exists(), reason="serving bundle missing")
def test_build_index_creates_outputs_in_empty_cwd(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("build_index_script", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    subset = json.loads(CHUNKS.read_text(encoding="utf-8"))[:150]
    src = tmp_path / "chunks.json"
    src.write_text(json.dumps(subset, ensure_ascii=False), encoding="utf-8")
    store = QdrantVectorStore(collection="t", dimension=DIM, path=str(tmp_path / "q"))
    monkeypatch.setattr(mod, "missing_requirements", lambda: [])
    monkeypatch.setattr(mod, "build_embedder", lambda: _Hash())
    monkeypatch.setattr(mod, "build_vector_store", lambda: store)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)

    mod.main(["--input", str(src)])

    assert store.client.count("t").count == 150
    assert np.load(work / "data/processed/baseline_embeddings.npy").shape == (150, DIM)
    manifest = json.loads((work / "data/processed/index_manifest.json").read_text())
    assert manifest["num_chunks"] == 150
    mod.main(["--input", str(src)])  # idempotent re-run (the compose `indexer` runs every start)
    assert store.client.count("t").count == 150

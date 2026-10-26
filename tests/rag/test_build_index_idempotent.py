"""Tests for idempotent behavior of build_index script when index already exists."""

import hashlib
import importlib.util
import json
import pathlib

import pytest

from rag.embedding.embedder import BaseEmbedder
from rag.indexing.vector_store import QdrantVectorStore

# Reuse same CHUNKS path as other test
CHUNKS = pathlib.Path(__file__).resolve().parents[2] / "data/serving/chunks.json"
SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts/data/build_index.py"
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
def test_build_index_idempotent_message_and_no_duplicate_points(tmp_path, monkeypatch, capsys):
    # Load the script as a module
    spec = importlib.util.spec_from_file_location("build_index_script", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Prepare a subset of chunks (150 items) and write to temporary input file
    subset = json.loads(CHUNKS.read_text(encoding="utf-8"))[:150]
    src = tmp_path / "chunks.json"
    src.write_text(json.dumps(subset, ensure_ascii=False), encoding="utf-8")

    # Create a fresh Qdrant vector store in a temporary directory
    store = QdrantVectorStore(collection="t", dimension=DIM, path=str(tmp_path / "q"))

    # Monkeypatch the script's helper functions to use our test doubles
    monkeypatch.setattr(mod, "missing_requirements", lambda: [])
    monkeypatch.setattr(mod, "build_embedder", lambda: _Hash())
    monkeypatch.setattr(mod, "build_vector_store", lambda: store)

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)

    # First run: builds the index
    mod.main(["--input", str(src)])
    first_count = store.client.count("t").count
    assert first_count == 150

    # Second run: should detect existing index and print the message
    mod.main(["--input", str(src)])
    captured = capsys.readouterr()
    assert "Index already built, skipping upsert" in captured.out

    # Ensure point count has not increased
    second_count = store.client.count("t").count
    assert second_count == 150

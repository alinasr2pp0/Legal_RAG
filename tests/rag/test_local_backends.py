import sys
import types

from core.config import Settings
from core.models import Chunk
from rag.indexing.factory import missing_requirements
from rag.indexing.vector_store import QdrantVectorStore


def _chunks() -> list[Chunk]:
    return [
        Chunk(chunk_id=f"article_{i}_p0", text=f"نص {i}", article_ids=[f"article_{i}"],
              metadata={"number": i, "is_repealed": i == 2, "book": None})
        for i in (1, 2, 3)
    ]


def test_qdrant_roundtrip_preserves_bool_and_drops_none(tmp_path):
    store = QdrantVectorStore(collection="t", dimension=3, path=str(tmp_path / "q"))
    store.upsert(_chunks(), [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    assert store.count() == 3
    hit = store.query([0, 1, 0], top_k=1)[0]
    assert hit.chunk.chunk_id == "article_2_p0" and hit.chunk.text == "نص 2"
    assert hit.chunk.metadata["is_repealed"] is True
    assert "book" not in hit.chunk.metadata


def test_qdrant_upsert_is_idempotent(tmp_path):
    store = QdrantVectorStore(collection="t", dimension=3, path=str(tmp_path / "q"))
    for _ in range(2):
        store.upsert(_chunks(), [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    assert store.count() == 3


def test_local_embedder_with_stub_model(monkeypatch):
    import numpy as np

    class FakeST:
        def __init__(self, name):
            self.name = name

        def encode(self, texts, **kw):
            assert kw["normalize_embeddings"] is True
            return np.ones((len(texts), 4))

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=FakeST)
    )
    from rag.embedding.embedder import LocalEmbedder

    e = LocalEmbedder(model_name="stub")
    assert e.embed_query("س") == [1.0] * 4
    assert len(e.embed_documents(["a", "b"])) == 2


def test_missing_requirements_reports_local_only_violations():
    assert missing_requirements(Settings(_env_file=None, local_only=False)) == []
    bad = Settings(_env_file=None, local_only=True,
                   llm_base_url="https://openrouter.ai/api/v1")
    assert any(p.startswith("LOCAL_ONLY") for p in missing_requirements(bad))

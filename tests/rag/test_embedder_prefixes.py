import numpy as np

from core.config import Settings
from rag.embedding.embedder import LocalEmbedder, prefixes_for


class _FakeST:
    def __init__(self):
        self.seen: list[str] = []

    def encode(self, texts, **_):
        self.seen += texts
        return np.ones((len(texts), 4))

    def get_sentence_embedding_dimension(self):
        return 4


def _embedder(name: str) -> LocalEmbedder:
    emb = LocalEmbedder.__new__(LocalEmbedder)
    emb.model_name, emb.batch_size, emb.model = name, 8, _FakeST()
    emb.query_prefix, emb.doc_prefix = prefixes_for(name)
    return emb


def test_e5_gets_query_and_passage_prefixes():
    emb = _embedder("intfloat/multilingual-e5-small")
    emb.embed_query("س")
    emb.embed_documents(["ن"])
    assert emb.model.seen == ["query: س", "passage: ن"] and emb.dimension == 4


def test_other_models_get_no_prefix():
    emb = _embedder("BAAI/bge-m3")
    emb.embed_query("س")
    assert emb.model.seen == ["س"]


def test_embedding_model_env_alias(monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
    assert Settings(_env_file=None).local_embedding_model == "intfloat/multilingual-e5-small"
    monkeypatch.delenv("EMBEDDING_MODEL")


def test_local_folder_path_prefixes_and_override():
    from rag.embedding.embedder import prefixes_for

    assert prefixes_for(r"D:\AI-Models\multilingual-e5-small")[0] == "query: "
    assert prefixes_for(r"D:\AI-Models\embedding-model") == ("", "")
    assert prefixes_for(r"D:\AI-Models\embedding-model", force=True)[0] == "query: "
    assert prefixes_for("intfloat/multilingual-e5-small", force=False) == ("", "")


def test_index_manifest_treats_local_copy_and_hub_id_as_same_model():
    from rag.indexing.manifest import model_id

    assert model_id(r"D:\AI-Models\multilingual-e5-small") == model_id(
        "intfloat/multilingual-e5-small"
    )

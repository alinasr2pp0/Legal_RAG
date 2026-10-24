import httpx
import pytest

from core.config import Settings, settings
from core.local_only import local_only_violations
from core.models import Chunk, ScoredChunk
from rag.indexing import factory
from rag.reranking.reranker import PassThroughReranker, VoyageReranker
from rag.reranking.exceptions import RerankerUnavailableError


def _c(cid: str, text: str, **meta) -> ScoredChunk:
    chunk = Chunk(chunk_id=cid, text=text, article_ids=[cid], metadata=meta)
    return ScoredChunk(chunk=chunk, score=0.1)


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return {"data": self._data}


def test_voyage_reranks_by_relevance_and_sends_only_article_text(monkeypatch):
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json)
        return _Resp([{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2}])

    monkeypatch.setattr(httpx, "post", fake_post)
    cands = [_c("a", "نص أ"), _c("b", "نص ب"), _c("case", "مستند خاص", source="case")]
    out = VoyageReranker(api_key="k", model="rerank-2.5").rerank("سؤال", cands, 3)
    assert [x.chunk.chunk_id for x in out] == ["b", "a", "case"]
    assert seen["url"].endswith("/rerank") and seen["headers"]["Authorization"] == "Bearer k"
    assert seen["json"]["documents"] == ["نص أ", "نص ب"]  # private case text never leaves
    assert seen["json"]["model"] == "rerank-2.5"


def test_voyage_requires_key():
    with pytest.raises(RuntimeError):
        VoyageReranker(api_key="")


def test_factory_selects_voyage_and_degrades_without_key(monkeypatch):
    monkeypatch.setattr(settings, "reranker_enabled", True)
    monkeypatch.setattr(settings, "reranker_required", False)
    monkeypatch.setattr(settings, "voyage_api_key", "k")
    assert isinstance(factory.build_reranker(), VoyageReranker)
    monkeypatch.setattr(settings, "voyage_api_key", "")
    assert isinstance(factory.build_reranker(), PassThroughReranker)
    monkeypatch.setattr(settings, "reranker_required", True)
    with pytest.raises(RerankerUnavailableError):
        factory.build_reranker()
        factory.build_reranker()


def test_local_only_rejects_voyage_but_open_mode_allows_it():
    bad = Settings(_env_file=None, local_only=True, reranker_enabled=True)
    assert any("Voyage" in p for p in local_only_violations(bad))
    ok = Settings(_env_file=None, local_only=False, reranker_enabled=True)
    assert local_only_violations(ok) == []

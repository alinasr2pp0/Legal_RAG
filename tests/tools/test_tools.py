import httpx

from core.config import settings
from core.models import Chunk
from rag.retrieval.hybrid import HybridRetriever
from rag.retrieval.sparse import BM25Index
from tools.search_documents import SearchDocumentsTool
from tools.tavily_search import TavilySearchTool


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_tavily_noop_without_key_or_flag(monkeypatch):
    monkeypatch.setattr(settings, "web_search_enabled", True)
    tool = TavilySearchTool(api_key="", client=_client(lambda r: httpx.Response(500)))
    assert not tool.available and tool("x") == []
    monkeypatch.setattr(settings, "web_search_enabled", False)
    assert TavilySearchTool(api_key="k").available is False


LEGAL = "المادة 163 كل خطأ سبب ضررا للغير يلزم من ارتكبه بالتعويض عن العقد والمسؤولية"


def _item(**kw):
    base = {"content": LEGAL, "url": "https://manshurat.org/x", "score": 0.8}
    base.update(kw)
    return base


def _run(items, monkeypatch, articles=None, **settings_kw):
    monkeypatch.setattr(settings, "web_search_enabled", True)
    monkeypatch.setattr(settings, "local_only", False)
    for k, v in settings_kw.items():
        monkeypatch.setattr(settings, k, v)
    tool = TavilySearchTool(
        api_key="k",
        client=_client(lambda r: httpx.Response(200, json={"results": items})),
    )
    return tool("q", articles)


def test_tavily_parses_results_as_web_chunks(monkeypatch):
    out = _run([_item(), _item(content="")], monkeypatch)
    assert len(out) == 1
    assert out[0].chunk.metadata["source"] == "web" and "number" not in out[0].chunk.metadata


def test_tavily_drops_non_allowlisted_domain(monkeypatch):
    assert _run([_item(url="https://evil.example.com/a")], monkeypatch) == []


def test_tavily_drops_low_score(monkeypatch):
    assert _run([_item(score=0.1)], monkeypatch) == []


def test_tavily_drops_non_legal_content(monkeypatch):
    assert _run([_item(content="وصفة كبسة لذيذة مع الارز واللحم")], monkeypatch) == []


def test_tavily_drops_wrong_article(monkeypatch):
    other = "المادة 999 تعويض ضرر عقد مسؤولية"
    assert _run([_item(content=other)], monkeypatch, articles=[163]) == []
    assert len(_run([_item()], monkeypatch, articles=[163])) == 1


def test_tavily_truncates_and_limits(monkeypatch):
    items = [_item(content=LEGAL + " " + "ضرر " * 500) for _ in range(6)]
    out = _run(items, monkeypatch, web_max_results=2)
    assert len(out) == 2
    assert all(len(c.chunk.text) <= settings.web_max_snippet_chars + 50 for c in out)


def test_tavily_blocked_in_local_only(monkeypatch):
    assert _run([_item()], monkeypatch, local_only=True) == []


def test_tavily_swallows_http_errors(monkeypatch):
    monkeypatch.setattr(settings, "web_search_enabled", True)
    monkeypatch.setattr(settings, "local_only", False)
    tool = TavilySearchTool(api_key="k", client=_client(lambda r: httpx.Response(500)))
    assert tool("q") == []


def test_search_tool_pins_requested_article_over_reranker():
    chunks = [
        Chunk(chunk_id=f"article_{n}_p0", text=t, article_ids=[f"article_{n}"],
              metadata={"number": n})
        for n, t in [(163, "ضرر خطأ تعويض"), (164, "تمييز مسؤولية"), (165, "قوة قاهرة")]
    ]
    index = BM25Index(chunks)

    class FakeStore:
        def query(self, e, top_k):
            return []

    class FakeEmb:
        def embed_query(self, t):
            return [0.0]

    class LastFirst:  # a reranker that would demote article 163
        def rerank(self, q, c, top_k):
            return list(reversed(c))[:top_k]

    retriever = HybridRetriever(FakeEmb(), FakeStore(), index)
    tool = SearchDocumentsTool(retriever, LastFirst(), 10, 3)
    result = tool("اشرح المادة 163 قوة قاهرة")
    assert result.chunks[0].chunk.metadata["number"] == 163
    assert result.pinned_articles == [163]

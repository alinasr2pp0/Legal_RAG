from core.models import Article
from rag.chunking.chunker import ArticleAwareChunker


def test_short_article_produces_single_chunk():
    chunker = ArticleAwareChunker(max_chars=1000)
    article = Article(article_id="article_1", number=1, text="نص قصير")
    chunks = chunker.chunk([article])
    assert len(chunks) == 1
    assert chunks[0].article_ids == ["article_1"]


def test_long_article_is_split_with_overlap():
    chunker = ArticleAwareChunker(max_chars=50, overlap_chars=10)
    long_text = "كلمة " * 100
    article = Article(article_id="article_2", number=2, text=long_text)
    chunks = chunker.chunk([article])
    assert len(chunks) > 1
    assert all(c.article_ids == ["article_2"] for c in chunks)

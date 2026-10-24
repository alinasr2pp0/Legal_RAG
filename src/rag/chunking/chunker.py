"""Article-aware chunking: chunks respect article boundaries instead of
splitting mid-legal-clause. Long articles are split with overlap; short
consecutive articles in the same chapter can optionally be merged."""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.models import Article, Chunk

DEFAULT_MAX_CHARS = 1200
DEFAULT_OVERLAP_CHARS = 150
MISSING_TEXT_MARKER = "[نص المادة غير متوفر في المصدر]"
INCOMPLETE_TEXT_MARKER = "[تنبيه: الفقرة (1) من هذه المادة غير متوفرة في المصدر العربي]"


class BaseChunker(ABC):
    @abstractmethod
    def chunk(self, articles: list[Article]) -> list[Chunk]: ...


class ArticleAwareChunker(BaseChunker):
    def __init__(
        self,
        max_chars: int = DEFAULT_MAX_CHARS,
        overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    ) -> None:
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def chunk(self, articles: list[Article]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for article in articles:
            if len(article.text) <= self.max_chars:
                chunks.append(self._make_chunk(article, article.text, part=0))
                continue

            start = 0
            part = 0
            while start < len(article.text):
                end = min(start + self.max_chars, len(article.text))
                segment = article.text[start:end]
                chunks.append(self._make_chunk(article, segment, part=part))
                part += 1
                start = end - self.overlap_chars if end < len(article.text) else end
        return chunks

    def _make_chunk(self, article: Article, text: str, part: int) -> Chunk:
        # Contextual header: the chapter title ("الفصل الرابع. الأثراء بلا سبب") is
        # strong retrieval signal for BM25 and for the embedding, and gives the
        # LLM the topic; it lives in metadata AND is prefixed to the chunk text.
        if article.text_incomplete and part == 0:
            text = f"{INCOMPLETE_TEXT_MARKER} {text}"
        if article.text_missing:
            # Deliberately NOT legal text: marks the gap so nothing downstream can mistake the
            # chapter heading for the article's content (see Orchestrator + /article/{n}).
            text = MISSING_TEXT_MARKER
        if article.chapter:
            text = f"{article.chapter}. {text}"
        return Chunk(
            chunk_id=f"{article.article_id}_p{part}",
            text=text,
            article_ids=[article.article_id],
            metadata={**article.to_metadata(), "chunk_part": part},
        )

"""Core domain models shared across the pipeline."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ArticleType(str, Enum):
    """Structural unit type inside the Civil Code."""

    BOOK = "book"        # كتاب
    PART = "part"         # باب
    CHAPTER = "chapter"   # فصل
    ARTICLE = "article"   # مادة


class Article(BaseModel):
    """A single legal article extracted from the Civil Code PDF."""

    article_id: str = Field(..., description="Stable id, e.g. 'article_163'")
    number: int = Field(..., description="Article number as printed in the code")
    text: str = Field("", description="Arabic text; may be empty only when is_repealed=True")
    text_en: str | None = Field(None, description="Official English translation, if extracted")
    book: str | None = None
    part: str | None = None
    chapter: str | None = None
    is_repealed: bool = Field(
        False, description="True if this article was repealed by a later law/decree"
    )
    page_number: int | None = None
    source_file: str | None = None
    text_incomplete: bool = Field(
        False,
        description="True when the source is known to lack part of the article (see "
        "ingestion/source_corrections.py); answers must carry a caveat",
    )

    @property
    def text_missing(self) -> bool:
        """True when the source has no Arabic text for a (non-repealed) article, e.g. Article 1022
        in the supplied PDF. Such an article must never be answered from its chapter heading."""
        return not self.text.strip() and not self.is_repealed

    def to_metadata(self) -> dict[str, str | int | bool | None]:
        return {
            "article_id": self.article_id,
            "number": self.number,
            "is_repealed": self.is_repealed,
            "text_missing": self.text_missing,
            "text_incomplete": self.text_incomplete,
            "book": self.book,
            "part": self.part,
            "chapter": self.chapter,
            "page_number": self.page_number,
        }


class Chunk(BaseModel):
    """A retrieval unit derived from one or more articles."""

    chunk_id: str
    text: str
    article_ids: list[str]
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ScoredChunk(BaseModel):
    chunk: Chunk
    score: float


class Citation(BaseModel):
    article_id: str
    article_number: int
    snippet: str
    citation: str = ""

    def model_post_init(self, __context: object) -> None:
        if not self.citation:
            self.citation = f"Egyptian Civil Code, Article {self.article_number}"


class AskRequest(BaseModel):
    """Request model for an ask/query endpoint.
    Includes optional debug flag to return retrieval diagnostics.
    """
    question: str = Field(..., description="User query or question")
    debug: bool = Field(False, description="Return retrieval diagnostics when true")


class AskResponse(BaseModel):
    """Response model for an ask/query.
    Mirrors what the API returns: answer text, optional latency, and related data.
    """
    answer: str = Field(..., description="Generated answer text")
    citations: list[Citation] = Field(default_factory=list, description="List of citations used in the answer")
    contexts: list[str] = Field(default_factory=list, description="Relevant context excerpts")
    latency_ms: float | None = Field(None, description="Optional latency in milliseconds")
    debug_info: list[dict] | None = Field(None, description="Optional retrieval diagnostics when debug flag is true")

class RagAnswer(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    contexts: list[str]
    latency_ms: float | None = None
    question: str
    answer: str
    citations: list[Citation]
    contexts: list[str]
    latency_ms: float | None = None

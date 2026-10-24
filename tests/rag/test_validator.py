from core.models import Article
from rag.ingestion.validator import ArticleValidator


def _article(number: int, text: str = "نص المادة القانونية الكامل") -> Article:
    return Article(article_id=f"article_{number}", number=number, text=text)


def test_valid_sequential_articles():
    validator = ArticleValidator()
    report = validator.validate([_article(1), _article(2), _article(3)])
    assert report.is_valid
    assert report.missing_numbers == []


def test_detects_duplicates():
    validator = ArticleValidator()
    report = validator.validate([_article(1), _article(1)])
    assert report.duplicate_numbers == [1]
    assert not report.is_valid


def test_detects_missing_numbers():
    validator = ArticleValidator()
    report = validator.validate([_article(1), _article(3)])
    assert report.missing_numbers == [2]


def test_detects_too_short_article():
    validator = ArticleValidator()
    report = validator.validate([_article(1, text="قص")])
    assert report.errors

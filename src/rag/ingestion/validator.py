"""Validate parsed articles before they enter the DVC-tracked dataset."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.models import Article

MIN_ARTICLE_LENGTH = 5


@dataclass
class ValidationReport:
    total: int
    valid: int
    errors: list[str] = field(default_factory=list)
    duplicate_numbers: list[int] = field(default_factory=list)
    missing_numbers: list[int] = field(default_factory=list)
    # articles whose source text is known to be absent/partial (never silently "valid")
    incomplete_numbers: list[int] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors and not self.duplicate_numbers


class ArticleValidator:
    def validate(self, articles: list[Article]) -> ValidationReport:
        errors: list[str] = []
        incomplete: list[int] = []
        seen: dict[int, int] = {}
        for article in articles:
            if not article.is_repealed and len(article.text.strip()) < MIN_ARTICLE_LENGTH:
                errors.append(f"article_{article.number}: text too short")
            seen[article.number] = seen.get(article.number, 0) + 1
            if article.text_incomplete or article.text_missing:
                incomplete.append(article.number)

        duplicates = sorted(n for n, count in seen.items() if count > 1)

        numbers = sorted(seen)
        missing: list[int] = []
        if numbers:
            expected = set(range(numbers[0], numbers[-1] + 1))
            missing = sorted(expected - set(numbers))

        return ValidationReport(
            total=len(articles),
            valid=len(articles) - len(errors),
            errors=errors,
            duplicate_numbers=duplicates,
            missing_numbers=missing,
            incomplete_numbers=sorted(incomplete),
        )

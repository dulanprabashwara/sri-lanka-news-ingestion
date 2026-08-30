from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ingestion.models import ExtractedArticle, Language, NormalizedArticle


def article_data() -> dict[str, object]:
    return {
        "source_slug": "fixture-news",
        "title": "  Fixture headline  ",
        "authors": (" Reporter One ", "Reporter   One", "", "Reporter Two"),
        "original_url": "https://news.example.com/story?utm_source=rss",
        "canonical_url": "https://news.example.com/story",
        "original_language": Language.ENGLISH,
        "published_at": datetime(
            2026, 8, 30, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))
        ),
        "discovered_at": datetime(2026, 8, 30, 5, 0, tzinfo=UTC),
        "article_text": "  Full fixture article text.  ",
    }


def test_article_normalizes_text_authors_and_utc_timestamps() -> None:
    article = ExtractedArticle.model_validate(article_data())

    assert article.title == "Fixture headline"
    assert article.article_text == "Full fixture article text."
    assert article.authors == ("Reporter One", "Reporter Two")
    assert article.published_at == datetime(2026, 8, 30, 4, 30, tzinfo=UTC)


def test_normalized_article_uses_the_same_validated_contract() -> None:
    article = NormalizedArticle.model_validate(article_data())
    assert article.source_slug == "fixture-news"
    assert article.original_language is Language.ENGLISH


@pytest.mark.parametrize("field", ["published_at", "discovered_at"])
def test_article_rejects_naive_timestamps(field: str) -> None:
    data = article_data()
    data[field] = datetime(2026, 8, 30, 5, 0)

    with pytest.raises(ValidationError, match="timezone"):
        ExtractedArticle.model_validate(data)


def test_article_rejects_invalid_source_slug() -> None:
    data = article_data()
    data["source_slug"] = "Fixture News"

    with pytest.raises(ValidationError):
        ExtractedArticle.model_validate(data)


def test_article_rejects_unknown_fields() -> None:
    data = article_data()
    data["summary"] = "AI fields do not belong here"

    with pytest.raises(ValidationError, match="Extra inputs"):
        ExtractedArticle.model_validate(data)

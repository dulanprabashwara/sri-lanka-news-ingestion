from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.models import DiscoveryCandidate
from ingestion.sources import NewsFirstAdapter, NewsFirstExtractionError

FIXTURES = Path(__file__).parent / "fixtures"
LISTING_URL = "https://www.newsfirst.lk/latest"
ARTICLE_URL = "https://www.newsfirst.lk/2026/08/30/fixture-ocean-story"


def settings() -> Settings:
    return Settings.model_validate(
        {"api_key": "test-secret", "http_user_agent": "SriLankaNewsIngestion/Test"}
    )


def response(content: bytes) -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            content=content,
            request=request,
        )
    )


def reference() -> DiscoveryCandidate:
    return DiscoveryCandidate.model_validate(
        {
            "source_slug": "newsfirst",
            "url": ARTICLE_URL,
            "discovered_at": datetime(2026, 8, 30, 2, 0, tzinfo=UTC),
        }
    )


def test_discovers_unique_newsfirst_article_links_from_latest_page() -> None:
    markup = (FIXTURES / "newsfirst-latest.html").read_bytes()
    discovered_at = datetime(2026, 8, 30, 2, 0, tzinfo=UTC)
    with HttpFetcher(settings(), transport=response(markup)) as fetcher:
        candidates = NewsFirstAdapter(
            fetcher, listing_url=LISTING_URL, now=lambda: discovered_at
        ).discover_recent()

    assert len(candidates) == 2
    assert str(candidates[0].url) == ARTICLE_URL
    assert candidates[0].discovered_at == discovered_at


def test_extracts_newsfirst_fields_and_converts_colombo_time_to_utc() -> None:
    markup = (FIXTURES / "newsfirst-article.html").read_bytes()
    with HttpFetcher(settings(), transport=response(markup)) as fetcher:
        adapter = NewsFirstAdapter(fetcher, listing_url=LISTING_URL)
        article = adapter.normalize(adapter.extract_article(reference()))

    assert article.title == "Fixture Ocean Story"
    assert article.authors == ("Staff Writer",)
    assert article.published_at == datetime(2026, 8, 30, 1, 53, tzinfo=UTC)
    assert str(article.canonical_url) == ARTICLE_URL
    assert article.original_language.value == "en"
    assert article.article_text == ("The first fixture paragraph.\n\nThe second fixture paragraph.")
    assert article.image is not None
    assert str(article.image.url) == "https://cdn.newsfirst.lk/fixture.jpg"


def test_rejects_newsfirst_article_without_body() -> None:
    markup = (FIXTURES / "newsfirst-malformed-article.html").read_bytes()
    with HttpFetcher(settings(), transport=response(markup)) as fetcher:
        adapter = NewsFirstAdapter(fetcher, listing_url=LISTING_URL)
        with pytest.raises(NewsFirstExtractionError, match="body is missing"):
            adapter.extract_article(reference())

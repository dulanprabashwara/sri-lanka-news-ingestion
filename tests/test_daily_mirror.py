from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.models import DiscoveryCandidate
from ingestion.sources import DailyMirrorAdapter, DailyMirrorExtractionError

FIXTURES = Path(__file__).parent / "fixtures"
FEED_URL = "https://www.dailymirror.lk/rss/breaking_news/108"
ARTICLE_URL = "https://www.dailymirror.lk/breaking-news/Fixture-prices-remain-stable/108-123456"


def settings() -> Settings:
    return Settings.model_validate(
        {
            "api_key": "test-secret",
            "http_user_agent": "SriLankaNewsIngestion/Test",
        }
    )


def test_discovers_daily_mirror_articles_from_official_rss_shape() -> None:
    feed = (FIXTURES / "daily-mirror-feed.xml").read_bytes()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            content=feed,
            request=request,
        )
    )
    discovered_at = datetime(2026, 8, 30, 6, 0, tzinfo=UTC)

    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = DailyMirrorAdapter(
            fetcher,
            feed_url=FEED_URL,
            now=lambda: discovered_at,
        )
        candidates = adapter.discover_recent()

    assert len(candidates) == 2
    assert str(candidates[0].url) == ARTICLE_URL
    assert candidates[0].title == "Fixture prices remain stable"
    assert candidates[0].discovered_at == discovered_at
    assert candidates[0].published_at == datetime(2026, 8, 30, 5, 19, tzinfo=UTC)
    assert candidates[0].description == "Representative fixture description."


def test_extracts_json_ld_metadata_and_current_daily_mirror_body_markup() -> None:
    article_html = (FIXTURES / "daily-mirror-article.html").read_bytes()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            content=article_html,
            request=request,
        )
    )
    discovered_at = datetime(2026, 8, 30, 6, 0, tzinfo=UTC)

    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = DailyMirrorAdapter(fetcher, feed_url=FEED_URL)
        reference = DiscoveryCandidate.model_validate(
            {
                "source_slug": "daily-mirror",
                "url": ARTICLE_URL,
                "discovered_at": discovered_at,
            }
        )
        normalized = adapter.normalize(adapter.extract_article(reference))

    assert normalized.title == "Fixture prices remain stable"
    assert normalized.authors == ("DM Editorial",)
    assert normalized.published_at == datetime(2026, 8, 30, 5, 19, tzinfo=UTC)
    assert str(normalized.canonical_url) == ARTICLE_URL
    assert normalized.original_language.value == "en"
    assert normalized.article_text == (
        "Colombo (Daily Mirror) - The first fixture paragraph. "
        "The second fixture paragraph includes an editor's note."
    )
    assert normalized.image is not None
    assert str(normalized.image.url) == "https://cdn.example.com/daily-mirror-fixture.jpg"


def test_rejects_missing_daily_mirror_body() -> None:
    malformed = (FIXTURES / "daily-mirror-malformed-article.html").read_bytes()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=malformed,
            request=request,
        )
    )
    reference = DiscoveryCandidate.model_validate(
        {
            "source_slug": "daily-mirror",
            "url": "https://www.dailymirror.lk/breaking-news/Broken/108-999999",
            "discovered_at": datetime(2026, 8, 30, 6, 0, tzinfo=UTC),
            "published_at": datetime(2026, 8, 30, 5, 0, tzinfo=UTC),
        }
    )

    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = DailyMirrorAdapter(fetcher, feed_url=FEED_URL)
        with pytest.raises(DailyMirrorExtractionError, match="body is missing"):
            adapter.extract_article(reference)


def test_falls_back_to_rss_content_when_html_fetch_blocked() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            403,
            headers={"Content-Type": "text/html", "cf-mitigated": "challenge"},
            content=b"<html><head><title>Just a moment...</title></head></html>",
            request=request,
        )
    )
    discovered_at = datetime(2026, 8, 30, 6, 0, tzinfo=UTC)
    published_at = datetime(2026, 8, 30, 5, 19, tzinfo=UTC)
    reference = DiscoveryCandidate.model_validate(
        {
            "source_slug": "daily-mirror",
            "url": ARTICLE_URL,
            "title": "Fixture prices remain stable",
            "discovered_at": discovered_at,
            "published_at": published_at,
            "description": "Representative summary from RSS feed.",
            "content": "Full article paragraph 1 from RSS feed.\n\nFull article paragraph 2.",
            "image_url": "https://cdn.example.com/daily-mirror-fixture.jpg",
        }
    )

    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = DailyMirrorAdapter(fetcher, feed_url=FEED_URL)
        normalized = adapter.normalize(adapter.extract_article(reference))

    assert normalized.title == "Fixture prices remain stable"
    assert normalized.published_at == published_at
    assert str(normalized.canonical_url) == ARTICLE_URL
    assert normalized.original_language.value == "en"
    assert normalized.article_text == "Full article paragraph 1 from RSS feed.\n\nFull article paragraph 2."
    assert normalized.summary == "Representative summary from RSS feed."
    assert normalized.image is not None
    assert str(normalized.image.url) == "https://cdn.example.com/daily-mirror-fixture.jpg"

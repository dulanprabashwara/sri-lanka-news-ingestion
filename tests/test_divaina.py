from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.models import DiscoveryCandidate
from ingestion.sources import DivainaAdapter, DivainaExtractionError

FIXTURES = Path(__file__).parent / "fixtures"
FEED_URL = "https://www.divaina.lk/feed"
ARTICLE_URL = "https://www.divaina.lk/test-article/"


def settings() -> Settings:
    return Settings.model_validate(
        {
            "api_key": "test-secret",
            "http_user_agent": "SriLankaNewsIngestion/Test",
        }
    )


def test_discovers_divaina_articles_from_rss() -> None:
    feed = (FIXTURES / "divaina-feed.xml").read_bytes()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/xml; charset=UTF-8"},
            content=feed,
            request=request,
        )
    )
    discovered_at = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)

    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = DivainaAdapter(
            fetcher,
            feed_url=FEED_URL,
            now=lambda: discovered_at,
        )
        candidates = adapter.discover_recent()

    assert len(candidates) == 1
    assert str(candidates[0].url) == ARTICLE_URL
    assert candidates[0].title == "Test Divaina Title"
    assert candidates[0].discovered_at == discovered_at


def test_extracts_divaina_article_body() -> None:
    article_html = (FIXTURES / "divaina-article.html").read_bytes()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            content=article_html,
            request=request,
        )
    )
    discovered_at = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)

    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = DivainaAdapter(fetcher, feed_url=FEED_URL)
        reference = DiscoveryCandidate.model_validate(
            {
                "source_slug": "divaina",
                "url": ARTICLE_URL,
                "discovered_at": discovered_at,
            }
        )
        normalized = adapter.normalize(adapter.extract_article(reference))

    assert normalized.title == "Test Divaina Title"
    assert normalized.authors == ("Divaina Author",)
    assert normalized.published_at == datetime(2026, 9, 3, 6, 30, tzinfo=UTC)
    assert str(normalized.canonical_url) == ARTICLE_URL
    assert normalized.original_language.value == "si"
    assert normalized.article_text == "Divaina paragraph 1."


def test_rejects_missing_divaina_body() -> None:
    malformed = (FIXTURES / "divaina-malformed.html").read_bytes()
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
            "source_slug": "divaina",
            "url": ARTICLE_URL,
            "discovered_at": datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
            "published_at": datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
        }
    )

    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = DivainaAdapter(fetcher, feed_url=FEED_URL)
        with pytest.raises(DivainaExtractionError, match="body is missing"):
            adapter.extract_article(reference)

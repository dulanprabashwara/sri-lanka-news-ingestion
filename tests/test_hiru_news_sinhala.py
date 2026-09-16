from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.models import DiscoveryCandidate
from ingestion.sources import HiruNewsSinhalaAdapter, HiruNewsSinhalaExtractionError

FIXTURES = Path(__file__).parent / "fixtures"
LISTING_URL = "https://www.hirunews.lk/"
ARTICLE_URL = "https://hirunews.lk/485779/fixture-river-story"


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
            "source_slug": "hiru-news-sinhala",
            "url": ARTICLE_URL,
            "discovered_at": datetime(2026, 8, 30, 10, 0, tzinfo=UTC),
            "published_at": datetime(2026, 8, 30, 9, 27, tzinfo=UTC),
        }
    )


def test_discovers_unique_hiru_articles_and_converts_listing_time() -> None:
    markup = (FIXTURES / "hiru-news-sinhala-listing.html").read_bytes()
    with HttpFetcher(settings(), transport=response(markup)) as fetcher:
        candidates = HiruNewsSinhalaAdapter(
            fetcher,
            listing_url=LISTING_URL,
            now=lambda: datetime(2026, 8, 30, 10, 0, tzinfo=UTC),
        ).discover_recent()

    assert [str(candidate.url) for candidate in candidates] == [
        ARTICLE_URL,
        "https://www.hirunews.lk/sports/485745/fixture-sports-story",
    ]
    assert candidates[0].title == "ගං ඉවුරෙන් හමුවූ පරීක්ෂණ පුවත"
    assert candidates[0].published_at == datetime(2026, 8, 30, 9, 27, tzinfo=UTC)
    assert candidates[1].published_at == datetime(2026, 8, 30, 4, 14, tzinfo=UTC)


def test_falls_back_to_latest_sinhala_sitemap_when_listing_returns_403() -> None:
    index = (FIXTURES / "hiru-news-sinhala-sitemap-index.xml").read_bytes()
    sitemap = (FIXTURES / "hiru-news-sinhala-sitemap.xml").read_bytes()
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if str(request.url) == LISTING_URL:
            return httpx.Response(403, request=request)
        if request.url.path == "/sitemap.xml":
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html; charset=UTF-8"},
                content=index,
                request=request,
            )
        if request.url.path == "/sitemaps/sinhala-244000.xml":
            return httpx.Response(
                200,
                headers={"Content-Type": "text/xml; charset=UTF-8"},
                content=sitemap,
                request=request,
            )
        return httpx.Response(404, request=request)

    with HttpFetcher(settings(), transport=httpx.MockTransport(handler)) as fetcher:
        candidates = HiruNewsSinhalaAdapter(
            fetcher,
            listing_url=LISTING_URL,
            now=lambda: datetime(2026, 9, 16, 12, 0, tzinfo=UTC),
        ).discover_recent()

    assert requested == [
        LISTING_URL,
        "https://www.hirunews.lk/sitemap.xml",
        "https://www.hirunews.lk/sitemaps/sinhala-244000.xml",
    ]
    assert [str(candidate.url) for candidate in candidates] == [
        ARTICLE_URL,
        "https://www.hirunews.lk/sports/485745/fixture-sports-story",
    ]
    assert candidates[0].title == "ගං ඉවුරෙන් හමුවූ පරීක්ෂණ පුවත"
    assert candidates[0].discovered_at == datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def test_extracts_hiru_article_and_preserves_sinhala_unicode() -> None:
    markup = (FIXTURES / "hiru-news-sinhala-article.html").read_bytes()
    with HttpFetcher(settings(), transport=response(markup)) as fetcher:
        adapter = HiruNewsSinhalaAdapter(fetcher, listing_url=LISTING_URL)
        article = adapter.normalize(adapter.extract_article(reference()))

    assert article.title == "ගං ඉවුරෙන් හමුවූ පරීක්ෂණ පුවත"
    assert article.authors == ("හිරු ප්‍රවෘත්ති",)
    assert article.original_language.value == "si"
    assert article.published_at == datetime(2026, 8, 30, 9, 27, tzinfo=UTC)
    assert str(article.canonical_url) == ARTICLE_URL
    assert article.article_text == (
        "මෙය පළමු හිරු පරීක්ෂණ ඡේදයයි.\n\nසිංහල අන්තර්ගතය නිවැරදිව සුරැකිය යුතුයි."  # noqa: RUF001
    )
    assert article.image is not None
    assert str(article.image.url) == "https://cdn.hirunews.lk/fixture.jpg"


def test_rejects_hiru_listing_without_valid_links() -> None:
    markup = (FIXTURES / "hiru-news-sinhala-malformed-listing.html").read_bytes()
    with HttpFetcher(settings(), transport=response(markup)) as fetcher:
        adapter = HiruNewsSinhalaAdapter(fetcher, listing_url=LISTING_URL)
        with pytest.raises(
            HiruNewsSinhalaExtractionError,
            match="listing contained no article links",
        ):
            adapter.discover_recent()


def test_rejects_hiru_article_without_body() -> None:
    markup = (FIXTURES / "hiru-news-sinhala-malformed-article.html").read_bytes()
    with HttpFetcher(settings(), transport=response(markup)) as fetcher:
        adapter = HiruNewsSinhalaAdapter(fetcher, listing_url=LISTING_URL)
        with pytest.raises(HiruNewsSinhalaExtractionError, match="body is missing"):
            adapter.extract_article(reference())

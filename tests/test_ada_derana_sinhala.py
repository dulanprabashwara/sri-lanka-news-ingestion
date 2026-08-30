from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.models import DiscoveryCandidate
from ingestion.sources import (
    AdaDeranaSinhalaAdapter,
    AdaDeranaSinhalaExtractionError,
)

FIXTURES = Path(__file__).parent / "fixtures"
FEED_URL = "https://sinhala.adaderana.lk/rss.php"
HOMEPAGE_URL = "https://sinhala.adaderana.lk/"
ARTICLE_URL = "https://sinhala.adaderana.lk/news/200001/fixture-story"


def settings() -> Settings:
    return Settings.model_validate(
        {"api_key": "test-secret", "http_user_agent": "SriLankaNewsIngestion/Test"}
    )


def response(content: bytes, content_type: str = "text/html") -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": content_type},
            content=content,
            request=request,
        )
    )


def reference() -> DiscoveryCandidate:
    return DiscoveryCandidate.model_validate(
        {
            "source_slug": "ada-derana-sinhala",
            "url": ARTICLE_URL,
            "discovered_at": datetime(2026, 8, 30, 4, 0, tzinfo=UTC),
            "published_at": datetime(2026, 8, 30, 3, 40, tzinfo=UTC),
        }
    )


def fallback_transport(
    homepage: bytes, requests: list[str], *, feed_status: int = 403
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path == "/rss.php":
            return httpx.Response(feed_status, request=request)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=homepage,
            request=request,
        )

    return httpx.MockTransport(handler)


def test_discovers_sinhala_articles_and_interprets_local_feed_time() -> None:
    feed = (FIXTURES / "ada-derana-sinhala-feed.xml").read_bytes()
    discovered_at = datetime(2026, 8, 30, 4, 0, tzinfo=UTC)
    with HttpFetcher(settings(), transport=response(feed, "application/rss+xml")) as fetcher:
        candidates = AdaDeranaSinhalaAdapter(
            fetcher, feed_url=FEED_URL, now=lambda: discovered_at
        ).discover_recent()

    assert len(candidates) == 2
    assert str(candidates[0].url) == ARTICLE_URL
    assert candidates[0].title == "ශ්‍රී ලංකාවේ පරීක්ෂණ පුවත"
    assert candidates[0].published_at == datetime(2026, 8, 30, 3, 40, tzinfo=UTC)


def test_rss_403_automatically_uses_one_homepage_request() -> None:
    homepage = (FIXTURES / "ada-derana-sinhala-homepage.html").read_bytes()
    requests: list[str] = []
    transport = fallback_transport(homepage, requests)

    with HttpFetcher(settings(), transport=transport) as fetcher:
        candidates = AdaDeranaSinhalaAdapter(
            fetcher,
            feed_url=FEED_URL,
            homepage_url=HOMEPAGE_URL,
        ).discover_recent()

    assert requests == [FEED_URL, HOMEPAGE_URL]
    assert len(candidates) == 2


def test_homepage_discovers_only_valid_unique_links_in_document_order() -> None:
    homepage = (FIXTURES / "ada-derana-sinhala-homepage.html").read_bytes()
    with HttpFetcher(settings(), transport=fallback_transport(homepage, [])) as fetcher:
        candidates = AdaDeranaSinhalaAdapter(
            fetcher,
            feed_url=FEED_URL,
            homepage_url=HOMEPAGE_URL,
        ).discover_recent()

    assert [str(candidate.url) for candidate in candidates] == [
        "https://sinhala.adaderana.lk/news/200010/first-homepage-story",
        "https://sinhala.adaderana.lk/sports/200011/sports-homepage-story",
    ]
    assert candidates[0].title == "පළමු මුල්පිටු පුවත"
    assert candidates[1].title == "ක්‍රීඩා පුවත"


def test_rejects_homepage_without_valid_article_links() -> None:
    homepage = (FIXTURES / "ada-derana-sinhala-malformed-homepage.html").read_bytes()
    with HttpFetcher(settings(), transport=fallback_transport(homepage, [])) as fetcher:
        adapter = AdaDeranaSinhalaAdapter(
            fetcher,
            feed_url=FEED_URL,
            homepage_url=HOMEPAGE_URL,
        )
        with pytest.raises(
            AdaDeranaSinhalaExtractionError,
            match="homepage contained no article links",
        ):
            adapter.discover_recent()


def test_extracts_and_preserves_sinhala_unicode() -> None:
    markup = (FIXTURES / "ada-derana-sinhala-article.html").read_bytes()
    with HttpFetcher(settings(), transport=response(markup)) as fetcher:
        adapter = AdaDeranaSinhalaAdapter(fetcher, feed_url=FEED_URL)
        article = adapter.normalize(adapter.extract_article(reference()))

    assert article.title == "ශ්‍රී ලංකාවේ පරීක්ෂණ පුවත"
    assert article.authors == ("අද දෙරණ",)
    assert article.original_language.value == "si"
    assert article.published_at == datetime(2026, 8, 30, 3, 40, tzinfo=UTC)
    assert str(article.canonical_url) == ARTICLE_URL
    assert article.article_text == (
        "මෙය පළමු පරීක්ෂණ ඡේදයයි.\n\nසිංහල අක්ෂර නිවැරදිව සුරැකිය යුතුය."  # noqa: RUF001
    )


def test_rejects_ada_derana_sinhala_article_without_body() -> None:
    markup = (FIXTURES / "ada-derana-sinhala-malformed-article.html").read_bytes()
    with HttpFetcher(settings(), transport=response(markup)) as fetcher:
        adapter = AdaDeranaSinhalaAdapter(fetcher, feed_url=FEED_URL)
        with pytest.raises(AdaDeranaSinhalaExtractionError, match="body is missing"):
            adapter.extract_article(reference())

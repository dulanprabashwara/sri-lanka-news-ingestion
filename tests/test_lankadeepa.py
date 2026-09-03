from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.models import DiscoveryCandidate
from ingestion.sources import LankadeepaAdapter, LankadeepaExtractionError

FIXTURES = Path(__file__).parent / "fixtures"
HOMEPAGE_URL = "https://www.lankadeepa.lk/latest-news/1"
ARTICLE_URL = "https://www.lankadeepa.lk/category/test-title/123-456"


def settings() -> Settings:
    return Settings.model_validate(
        {
            "api_key": "test-secret",
            "http_user_agent": "SriLankaNewsIngestion/Test",
        }
    )


def test_discovers_lankadeepa_articles_from_html() -> None:
    homepage = (FIXTURES / "lankadeepa-homepage.html").read_bytes()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            content=homepage,
            request=request,
        )
    )
    discovered_at = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)

    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = LankadeepaAdapter(
            fetcher,
            homepage_url=HOMEPAGE_URL,
            now=lambda: discovered_at,
        )
        candidates = adapter.discover_recent()

    assert len(candidates) == 1
    assert str(candidates[0].url) == ARTICLE_URL
    assert candidates[0].title == "Test Lankadeepa Title"
    assert candidates[0].discovered_at == discovered_at


def test_extracts_lankadeepa_article_body() -> None:
    article_html = (FIXTURES / "lankadeepa-article.html").read_bytes()
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
        adapter = LankadeepaAdapter(fetcher, homepage_url=HOMEPAGE_URL)
        reference = DiscoveryCandidate.model_validate(
            {
                "source_slug": "lankadeepa",
                "url": ARTICLE_URL,
                "discovered_at": discovered_at,
            }
        )
        normalized = adapter.normalize(adapter.extract_article(reference))

    assert normalized.title == "Test Lankadeepa Title"
    assert normalized.authors == ("Lankadeepa Author",)
    assert normalized.published_at == datetime(2026, 9, 3, 6, 30, tzinfo=UTC)
    assert str(normalized.canonical_url) == ARTICLE_URL
    assert normalized.original_language.value == "si"
    assert normalized.article_text == "Lankadeepa paragraph 1."


def test_rejects_missing_lankadeepa_body() -> None:
    malformed = (FIXTURES / "lankadeepa-malformed.html").read_bytes()
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
            "source_slug": "lankadeepa",
            "url": ARTICLE_URL,
            "discovered_at": datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
            "published_at": datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
        }
    )

    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = LankadeepaAdapter(fetcher, homepage_url=HOMEPAGE_URL)
        with pytest.raises(LankadeepaExtractionError, match="body is missing"):
            adapter.extract_article(reference)

def test_extracts_lankadeepa_no_canonical_url() -> None:
    article_html = (FIXTURES / "lankadeepa-article-no-canonical.html").read_bytes()
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
        adapter = LankadeepaAdapter(fetcher, homepage_url=HOMEPAGE_URL)
        reference = DiscoveryCandidate.model_validate(
            {
                "source_slug": "lankadeepa",
                "url": ARTICLE_URL,
                "discovered_at": discovered_at,
            }
        )
        normalized = adapter.normalize(adapter.extract_article(reference))

    assert str(normalized.canonical_url) == ARTICLE_URL

def test_extracts_lankadeepa_fallback_canonical_url() -> None:
    article_html = (FIXTURES / "lankadeepa-article-no-og-url.html").read_bytes()
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
        adapter = LankadeepaAdapter(fetcher, homepage_url=HOMEPAGE_URL)
        reference = DiscoveryCandidate.model_validate(
            {
                "source_slug": "lankadeepa",
                "url": ARTICLE_URL,
                "discovered_at": discovered_at,
            }
        )
        normalized = adapter.normalize(adapter.extract_article(reference))

    assert str(normalized.canonical_url) == ARTICLE_URL


def test_lankadeepa_rejects_mismatched_og_url_article_id() -> None:
    """Article A: og:url points to article 999999 but page URL is 697229.
    The adapter must reject the mismatched og:url and use the fetched page URL."""
    article_html = (FIXTURES / "lankadeepa-article-a.html").read_bytes()
    article_a_url = "https://www.lankadeepa.lk/news/article-a/101-697229"
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
        adapter = LankadeepaAdapter(fetcher, homepage_url=HOMEPAGE_URL)
        reference = DiscoveryCandidate.model_validate(
            {
                "source_slug": "lankadeepa",
                "url": article_a_url,
                "discovered_at": discovered_at,
            }
        )
        normalized = adapter.normalize(adapter.extract_article(reference))

    # Must use the fetched page URL, NOT the mismatched og:url
    assert str(normalized.canonical_url) == article_a_url
    assert normalized.title == "Lankadeepa Article A Title"
    assert "Unique body content for article A" in normalized.article_text


def test_lankadeepa_accepts_matching_og_url_article_id() -> None:
    """Article B: og:url points to article 697230 and page URL is also 697230.
    The adapter must accept the matching og:url."""
    article_html = (FIXTURES / "lankadeepa-article-b.html").read_bytes()
    article_b_url = "https://www.lankadeepa.lk/news/article-b/101-697230"
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
        adapter = LankadeepaAdapter(fetcher, homepage_url=HOMEPAGE_URL)
        reference = DiscoveryCandidate.model_validate(
            {
                "source_slug": "lankadeepa",
                "url": article_b_url,
                "discovered_at": discovered_at,
            }
        )
        normalized = adapter.normalize(adapter.extract_article(reference))

    # og:url should be accepted since the article ID matches
    assert "697230" in str(normalized.canonical_url)
    assert normalized.title == "Lankadeepa Article B Title"
    assert "Unique body content for article B" in normalized.article_text


def test_lankadeepa_distinct_articles_produce_distinct_content() -> None:
    """Two different articles must produce different canonical URLs and bodies."""
    article_a_html = (FIXTURES / "lankadeepa-article-a.html").read_bytes()
    article_b_html = (FIXTURES / "lankadeepa-article-b.html").read_bytes()
    article_a_url = "https://www.lankadeepa.lk/news/article-a/101-697229"
    article_b_url = "https://www.lankadeepa.lk/news/article-b/101-697230"

    discovered_at = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)

    def make_transport(content: bytes) -> httpx.MockTransport:
        return httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"Content-Type": "text/html; charset=UTF-8"},
                content=content,
                request=request,
            )
        )

    with HttpFetcher(settings(), transport=make_transport(article_a_html)) as fetcher:
        adapter = LankadeepaAdapter(fetcher, homepage_url=HOMEPAGE_URL)
        ref_a = DiscoveryCandidate.model_validate(
            {"source_slug": "lankadeepa", "url": article_a_url, "discovered_at": discovered_at}
        )
        norm_a = adapter.normalize(adapter.extract_article(ref_a))

    with HttpFetcher(settings(), transport=make_transport(article_b_html)) as fetcher:
        adapter = LankadeepaAdapter(fetcher, homepage_url=HOMEPAGE_URL)
        ref_b = DiscoveryCandidate.model_validate(
            {"source_slug": "lankadeepa", "url": article_b_url, "discovered_at": discovered_at}
        )
        norm_b = adapter.normalize(adapter.extract_article(ref_b))

    # Must produce different canonical URLs
    assert str(norm_a.canonical_url) != str(norm_b.canonical_url)
    # Must produce different body text
    assert norm_a.article_text != norm_b.article_text
    # Both must have valid content
    assert norm_a.article_text
    assert norm_b.article_text

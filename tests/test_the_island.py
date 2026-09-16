from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from ingestion.config import Settings
from ingestion.extraction import parse_html
from ingestion.http import HttpFetcher
from ingestion.models import DiscoveryCandidate
from ingestion.sources import TheIslandAdapter, TheIslandExtractionError

FIXTURES = Path(__file__).parent / "fixtures"
FEED_URL = "http://island.lk/feed/"
ARTICLE_URL = "http://island.lk/test-article/"


def settings() -> Settings:
    return Settings.model_validate(
        {
            "api_key": "test-secret",
            "http_user_agent": "SriLankaNewsIngestion/Test",
        }
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


def test_discovers_the_island_articles_from_rss() -> None:
    feed = (FIXTURES / "the-island-feed.xml").read_bytes()
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
        adapter = TheIslandAdapter(
            fetcher,
            feed_url=FEED_URL,
            now=lambda: discovered_at,
        )
        candidates = adapter.discover_recent()

    assert len(candidates) == 1
    assert str(candidates[0].url) == ARTICLE_URL
    assert candidates[0].title == "Test Island Title"
    assert candidates[0].discovered_at == discovered_at


def test_extracts_the_island_article_body() -> None:
    article_html = (FIXTURES / "the-island-article.html").read_bytes()
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
        adapter = TheIslandAdapter(fetcher, feed_url=FEED_URL)
        reference = DiscoveryCandidate.model_validate(
            {
                "source_slug": "the-island",
                "url": ARTICLE_URL,
                "discovered_at": discovered_at,
            }
        )
        normalized = adapter.normalize(adapter.extract_article(reference))

    assert normalized.title == "Test Island Title"
    assert normalized.authors == ("Author Name",)
    assert normalized.published_at == datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    assert str(normalized.canonical_url) == ARTICLE_URL
    assert normalized.original_language.value == "en"
    assert normalized.article_text == "Island paragraph 1.\n\nIsland paragraph 2."


def test_rejects_missing_the_island_body() -> None:
    malformed = (FIXTURES / "the-island-malformed.html").read_bytes()
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
            "source_slug": "the-island",
            "url": ARTICLE_URL,
            "discovered_at": datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
            "published_at": datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
        }
    )

    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = TheIslandAdapter(fetcher, feed_url=FEED_URL)
        with pytest.raises(TheIslandExtractionError, match="body is missing"):
            adapter.extract_article(reference)


def test_extracts_the_island_article_body_v2() -> None:
    article_html = (FIXTURES / "the-island-article-v2.html").read_bytes()
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
        adapter = TheIslandAdapter(fetcher, feed_url=FEED_URL)
        reference = DiscoveryCandidate.model_validate(
            {
                "source_slug": "the-island",
                "url": ARTICLE_URL,
                "discovered_at": discovered_at,
            }
        )
        normalized = adapter.normalize(adapter.extract_article(reference))

    assert normalized.title == "Test Island Title V2"
    expected = "Island paragraph 1 (v2 format).\n\nIsland paragraph 2 (v2 format)."
    assert normalized.article_text == expected


def test_extracts_the_island_title_from_alternate_article_heading() -> None:
    article_html = (FIXTURES / "the-island-alternate-title.html").read_bytes()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            content=article_html,
            request=request,
        )
    )
    reference = DiscoveryCandidate.model_validate(
        {
            "source_slug": "the-island",
            "url": "https://island.lk/alternate-title-article/",
            "discovered_at": datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
        }
    )

    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = TheIslandAdapter(fetcher, feed_url=FEED_URL)
        normalized = adapter.normalize(adapter.extract_article(reference))

    assert normalized.title == "Alternate Island Article Title"
    assert normalized.article_text == "Island paragraph 1.\n\nIsland paragraph 2."


def test_the_island_title_falls_back_to_open_graph_then_document_title() -> None:
    with HttpFetcher(settings(), transport=response(b"")) as fetcher:
        adapter = TheIslandAdapter(fetcher, feed_url=FEED_URL)
        open_graph = parse_html(
            """
            <html><head>
              <title>Document fallback | The Island</title>
              <meta property="og:title" content="OpenGraph fallback | The Island">
            </head></html>
            """
        )
        document_only = parse_html(
            "<html><head><title>Document fallback | The Island</title></head></html>"
        )

        assert adapter._title(open_graph, {}) == "OpenGraph fallback"
        assert adapter._title(document_only, {}) == "Document fallback"


@pytest.mark.parametrize(
    "title",
    ["The Island", "You are being redirected...", "Just a moment...", "---"],
)
def test_the_island_rejects_generic_or_malformed_document_titles(title: str) -> None:
    document = parse_html(f"<html><head><title>{title}</title></head></html>")
    with HttpFetcher(settings(), transport=response(b"")) as fetcher:
        adapter = TheIslandAdapter(fetcher, feed_url=FEED_URL)
        with pytest.raises(TheIslandExtractionError, match="title is missing"):
            adapter._title(document, {})


def test_the_island_upgrades_http_canonical_to_https() -> None:
    """When a page redirects HTTP to HTTPS but the canonical link tag still says
    http://, the adapter must upgrade the canonical URL to https://."""
    article_html = (FIXTURES / "the-island-article-http-canonical.html").read_bytes()
    # Simulate: original URL was http:// but fetcher followed redirect to https://
    https_page_url = "https://island.lk/https-test-article/"
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
        adapter = TheIslandAdapter(fetcher, feed_url=FEED_URL)
        reference = DiscoveryCandidate.model_validate(
            {
                "source_slug": "the-island",
                "url": https_page_url,
                "discovered_at": discovered_at,
            }
        )
        normalized = adapter.normalize(adapter.extract_article(reference))

    # Canonical must be HTTPS, not HTTP
    assert str(normalized.canonical_url).startswith("https://")
    assert str(normalized.canonical_url) == https_page_url
    assert normalized.title == "HTTPS Test Island Title"

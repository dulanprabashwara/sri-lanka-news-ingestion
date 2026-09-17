from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from ingestion.backend import SubmissionResult, SubmissionStatus
from ingestion.config import Settings
from ingestion.extraction import parse_html
from ingestion.http import HttpFetcher
from ingestion.models import DiscoveryCandidate, NormalizedArticle
from ingestion.runner import run_once
from ingestion.sources import TheIslandAdapter, TheIslandExtractionError

FIXTURES = Path(__file__).parent / "fixtures"
FEED_URL = "http://island.lk/feed/"
ARTICLE_URL = "https://island.lk/test-article/"


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


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        ("<article><h1>Article heading</h1></article>", "Article heading"),
        ("<main><h1>Main heading</h1></main>", "Main heading"),
    ],
)
def test_the_island_title_uses_generic_heading_fallbacks(
    markup: str,
    expected: str,
) -> None:
    with HttpFetcher(settings(), transport=response(b"")) as fetcher:
        adapter = TheIslandAdapter(fetcher, feed_url=FEED_URL)
        assert adapter._title(parse_html(markup), {}) == expected


def test_rich_feed_preserves_order_metadata_and_normalizes_identity() -> None:
    feed = (FIXTURES / "the-island-feed-rich.xml").read_bytes()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "application/rss+xml; charset=UTF-8"},
            content=feed,
            request=request,
        )
    )
    discovered_at = datetime(2026, 9, 17, 2, 0, tzinfo=UTC)

    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = TheIslandAdapter(
            fetcher,
            feed_url=FEED_URL,
            now=lambda: discovered_at,
        )
        candidates = adapter.discover_recent()

    assert [str(candidate.url) for candidate in candidates] == [
        "https://island.lk/rich-feed-story/",
        "https://island.lk/second-feed-story/",
    ]
    assert candidates[0].title == "Rich Island Feed Story"
    assert candidates[0].published_at == datetime(2026, 9, 17, 0, 49, 27, tzinfo=UTC)
    assert candidates[0].description is not None
    assert candidates[0].description.startswith("The publisher supplied summary")
    assert candidates[0].content is not None
    assert "paragraph one" in candidates[0].content
    assert "Continue Reading" not in candidates[0].content
    assert str(candidates[0].image_url) == (
        "https://island.lk/wp-content/uploads/2026/09/feed-story.jpg"
    )


def test_challenge_uses_substantial_feed_fallback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    feed = (FIXTURES / "the-island-feed-rich.xml").read_bytes()
    challenge = (FIXTURES / "the-island-challenge.html").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/feed/":
            return httpx.Response(
                200,
                headers={"Content-Type": "application/rss+xml"},
                content=feed,
                request=request,
            )
        return httpx.Response(
            307,
            headers={"Content-Type": "text/html"},
            content=challenge,
            request=request,
        )

    caplog.set_level("INFO", logger="ingestion.sources.the_island")
    with HttpFetcher(settings(), transport=httpx.MockTransport(handler)) as fetcher:
        adapter = TheIslandAdapter(fetcher, feed_url=FEED_URL)
        candidate = adapter.discover_recent()[0]
        normalized = adapter.normalize(adapter.extract_article(candidate))

    assert normalized.title == "Rich Island Feed Story"
    assert normalized.authors == ("Island Reporter",)
    assert normalized.published_at == datetime(2026, 9, 17, 0, 49, 27, tzinfo=UTC)
    assert normalized.category is not None
    assert normalized.category.value == "LOCAL"
    assert normalized.summary is not None
    assert normalized.summary.startswith("The publisher supplied summary")
    assert "paragraph one" in normalized.article_text
    assert "sucuri_cloudproxy_js" not in normalized.article_text
    assert "Javascript is required" not in normalized.article_text
    assert normalized.image is not None
    assert str(normalized.image.url).endswith("/feed-story.jpg")
    assert str(normalized.original_url) == "https://island.lk/rich-feed-story/"
    assert str(normalized.canonical_url) == "https://island.lk/rich-feed-story/"
    assert "the_island_detail_challenged" in caplog.text
    assert "the_island_feed_fallback_used" in caplog.text


@pytest.mark.parametrize("status_code", [403, 429])
def test_access_restriction_uses_feed_fallback(status_code: int) -> None:
    feed = (FIXTURES / "the-island-feed-rich.xml").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/feed/":
            return httpx.Response(
                200,
                headers={"Content-Type": "application/rss+xml"},
                content=feed,
                request=request,
            )
        return httpx.Response(status_code, request=request)

    with HttpFetcher(settings(), transport=httpx.MockTransport(handler)) as fetcher:
        adapter = TheIslandAdapter(fetcher, feed_url=FEED_URL)
        candidate = adapter.discover_recent()[0]
        article = adapter.normalize(adapter.extract_article(candidate))

    assert article.title == "Rich Island Feed Story"
    assert len(article.article_text) >= adapter.MIN_FEED_BODY_CHARACTERS


def test_challenge_with_unusable_feed_metadata_remains_failure() -> None:
    challenge = (FIXTURES / "the-island-challenge.html").read_bytes()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            307,
            headers={"Content-Type": "text/html"},
            content=challenge,
            request=request,
        )
    )
    candidate = DiscoveryCandidate.model_validate(
        {
            "source_slug": "the-island",
            "url": "http://island.lk/tiny-feed-story/",
            "discovered_at": datetime(2026, 9, 17, 2, 0, tzinfo=UTC),
            "published_at": datetime(2026, 9, 17, 1, 0, tzinfo=UTC),
            "title": "Tiny Feed Story",
            "content": "A tiny teaser.",
        }
    )

    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = TheIslandAdapter(fetcher, feed_url=FEED_URL)
        with pytest.raises(TheIslandExtractionError, match="substantial article content"):
            adapter.extract_article(candidate)


def test_normal_detail_page_remains_preferred_over_feed_content() -> None:
    article_html = (FIXTURES / "the-island-article.html").read_bytes()
    candidate = DiscoveryCandidate.model_validate(
        {
            "source_slug": "the-island",
            "url": ARTICLE_URL,
            "discovered_at": datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
            "published_at": datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
            "title": "Feed title must not replace page title",
            "description": "Feed summary remains available when the page has none.",
            "content": (
                "Feed fallback content is substantial but must not replace a normal article "
                "detail response. It contains enough words and characters to qualify only "
                "when the publisher detail page is challenged or access restricted."
            ),
        }
    )

    with HttpFetcher(settings(), transport=response(article_html)) as fetcher:
        adapter = TheIslandAdapter(fetcher, feed_url=FEED_URL)
        normalized = adapter.normalize(adapter.extract_article(candidate))

    assert normalized.title == "Test Island Title"
    assert normalized.article_text == "Island paragraph 1.\n\nIsland paragraph 2."
    assert normalized.summary == "Feed summary remains available when the page has none."


def test_normal_parser_failure_does_not_silently_use_feed_fallback() -> None:
    malformed = (FIXTURES / "the-island-malformed.html").read_bytes()
    candidate = DiscoveryCandidate.model_validate(
        {
            "source_slug": "the-island",
            "url": ARTICLE_URL,
            "discovered_at": datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
            "published_at": datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
            "title": "Feed fallback must not hide parser defects",
            "content": (
                "This publisher feed content is intentionally substantial enough for the "
                "fallback quality gate. A normal HTML response with missing article markup "
                "must still surface the parser defect instead of silently using this text."
            ),
        }
    )

    with HttpFetcher(settings(), transport=response(malformed)) as fetcher:
        adapter = TheIslandAdapter(fetcher, feed_url=FEED_URL)
        with pytest.raises(TheIslandExtractionError, match="body is missing"):
            adapter.extract_article(candidate)


class _RememberingSubmitter:
    def __init__(self) -> None:
        self.seen: set[str] = set()

    def submit(self, article: NormalizedArticle) -> SubmissionResult:
        canonical_url = str(article.canonical_url)
        status = "DUPLICATE" if canonical_url in self.seen else "CREATED"
        self.seen.add(canonical_url)
        return SubmissionResult.model_validate(
            {
                "status": status,
                "articleId": canonical_url,
                "canonicalUrl": canonical_url,
            }
        )


def test_fallback_preserves_created_duplicate_and_run_limit_behavior() -> None:
    feed = (FIXTURES / "the-island-feed-rich.xml").read_bytes()
    challenge = (FIXTURES / "the-island-challenge.html").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/feed/":
            return httpx.Response(
                200,
                headers={"Content-Type": "application/rss+xml"},
                content=feed,
                request=request,
            )
        return httpx.Response(
            307,
            headers={"Content-Type": "text/html"},
            content=challenge,
            request=request,
        )

    submitter = _RememberingSubmitter()
    with HttpFetcher(settings(), transport=httpx.MockTransport(handler)) as fetcher:
        adapter = TheIslandAdapter(fetcher, feed_url=FEED_URL)
        first = run_once(adapter, submitter, limit=1)
        second = run_once(adapter, submitter, limit=1)

    assert first.discovered == 2
    assert first.processed == 1
    assert first.created == 1
    assert first.failed == 0
    assert second.processed == 1
    assert second.duplicates == 1
    assert second.failed == 0
    assert SubmissionStatus.CREATED.value == "CREATED"

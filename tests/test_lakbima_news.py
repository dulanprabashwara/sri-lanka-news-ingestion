from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from ingestion.backend import SubmissionResult, SubmissionStatus
from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.models import DiscoveryCandidate, NormalizedArticle
from ingestion.runner import run_once
from ingestion.sources import LakbimaNewsAdapter, LakbimaNewsExtractionError

FIXTURES = Path(__file__).parent / "fixtures"
FEED_URL = "https://lakbima.news/feed/"
ARTICLE_URL = "https://lakbima.news/sample-story/"
NOW = datetime(2026, 9, 17, 4, 0, tzinfo=UTC)


def settings() -> Settings:
    return Settings.model_validate(
        {"api_key": "test-secret", "http_user_agent": "SriLankaNewsIngestion/Test"}
    )


def test_discovers_rss_metadata_in_order_and_deduplicates_urls() -> None:
    feed = (FIXTURES / "lakbima-feed.xml").read_bytes()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "application/rss+xml"},
            content=feed,
            request=request,
        )
    )
    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = LakbimaNewsAdapter(fetcher, feed_url=FEED_URL, now=lambda: NOW)
        candidates = adapter.discover_recent()

    assert len(candidates) == 1
    candidate = candidates[0]
    assert str(candidate.url) == ARTICLE_URL
    assert candidate.title == "නවතම ලක්බිම පුවත"
    assert candidate.description == "මෙය පුවත පිළිබඳ ප්‍රකාශකයා ලබාදුන් සාරාංශයකි."
    assert candidate.content is not None and "තෙවන ඡේදය" in candidate.content
    assert candidate.published_at == datetime(2026, 9, 16, 21, 50, 51, tzinfo=UTC)


def test_extracts_detail_article_with_sinhala_metadata() -> None:
    markup = (FIXTURES / "lakbima-article.html").read_bytes()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            content=markup,
            request=request,
        )
    )
    candidate = DiscoveryCandidate.model_validate(
        {
            "source_slug": "lakbima-news",
            "url": ARTICLE_URL,
            "discovered_at": NOW,
            "published_at": NOW,
            "description": "ප්‍රකාශක සාරාංශය",
        }
    )
    with HttpFetcher(settings(), transport=transport) as fetcher:
        article = LakbimaNewsAdapter(fetcher, feed_url=FEED_URL).extract_article(candidate)

    assert article.title == "නවතම ලක්බිම පුවත"
    assert article.original_language.value == "si"
    assert article.authors == ("Pathum Dissanayake",)
    assert article.summary == "ප්‍රකාශක සාරාංශය"
    assert article.published_at == datetime(2026, 9, 16, 21, 50, 51, tzinfo=UTC)
    assert "දෙවන වැදගත් ඡේදය" in article.article_text
    assert article.image is not None
    assert str(article.image.url) == "https://lakbima.news/wp-content/uploads/story.jpg"


def test_uses_substantial_feed_content_when_detail_fetch_fails() -> None:
    feed = (FIXTURES / "lakbima-feed.xml").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/feed/":
            return httpx.Response(
                200,
                headers={"Content-Type": "application/rss+xml"},
                content=feed,
                request=request,
            )
        return httpx.Response(503, request=request)

    with HttpFetcher(settings(), transport=httpx.MockTransport(handler)) as fetcher:
        adapter = LakbimaNewsAdapter(fetcher, feed_url=FEED_URL, now=lambda: NOW)
        candidate = adapter.discover_recent()[0]
        article = adapter.extract_article(candidate)

    assert article.title == "නවතම ලක්බිම පුවත"
    assert article.authors == ("Pathum Dissanayake",)
    assert article.category is not None and article.category.value == "LOCAL"
    assert len(article.article_text) >= 200


def test_rejects_short_feed_fallback_and_challenge_html() -> None:
    candidate = DiscoveryCandidate.model_validate(
        {
            "source_slug": "lakbima-news",
            "url": ARTICLE_URL,
            "discovered_at": NOW,
            "published_at": NOW,
            "title": "නවතම ලක්බිම පුවත",
            "content": "කෙටි පුවතකි.",
        }
    )
    challenge = b"<html><title>Access denied</title><body>checking your browser</body></html>"
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=challenge,
            request=request,
        )
    )
    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = LakbimaNewsAdapter(fetcher, feed_url=FEED_URL)
        with pytest.raises(LakbimaNewsExtractionError, match="substantial content"):
            adapter.extract_article(candidate)


def test_http_www_tracking_and_trailing_slash_share_one_identity() -> None:
    normalized = LakbimaNewsAdapter._canonical_article_url(
        "http://www.lakbima.news/sample-story?utm_source=newsletter"
    )
    assert normalized == ARTICLE_URL


@pytest.mark.parametrize("status", [SubmissionStatus.CREATED, SubmissionStatus.DUPLICATE])
def test_runner_preserves_limit_and_submission_status(status: SubmissionStatus) -> None:
    feed = (FIXTURES / "lakbima-feed.xml").read_bytes()
    markup = (FIXTURES / "lakbima-article.html").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        content = feed if request.url.path == "/feed/" else markup
        content_type = "application/rss+xml" if request.url.path == "/feed/" else "text/html"
        return httpx.Response(
            200, headers={"Content-Type": content_type}, content=content, request=request
        )

    class Submitter:
        def submit(self, article: NormalizedArticle) -> SubmissionResult:
            return SubmissionResult.model_validate(
                {"status": status, "articleId": "article-1", "canonicalUrl": ARTICLE_URL}
            )

    with HttpFetcher(settings(), transport=httpx.MockTransport(handler)) as fetcher:
        summary = run_once(
            LakbimaNewsAdapter(fetcher, feed_url=FEED_URL, now=lambda: NOW),
            Submitter(),
            limit=1,
        )

    assert summary.processed == 1
    assert summary.created == (1 if status is SubmissionStatus.CREATED else 0)
    assert summary.duplicates == (1 if status is SubmissionStatus.DUPLICATE else 0)

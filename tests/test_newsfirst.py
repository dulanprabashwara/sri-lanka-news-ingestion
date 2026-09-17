from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from ingestion.config import Settings
from ingestion.http import HttpFetcher, HttpStatusError
from ingestion.models import DiscoveryCandidate
from ingestion.sources import NewsFirstAdapter, NewsFirstExtractionError

FIXTURES = Path(__file__).parent / "fixtures"
LISTING_URL = "https://www.newsfirst.lk/latest"
ARTICLE_URL = "https://www.newsfirst.lk/2026/08/30/fixture-ocean-story"


class FakeClock:
    def __init__(self) -> None:
        self.current = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += seconds


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


def test_spaces_first_article_request_after_discovery() -> None:
    listing = (FIXTURES / "newsfirst-latest.html").read_bytes()
    article = (FIXTURES / "newsfirst-article.html").read_bytes()
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        content = listing if request.url.path == "/latest" else article
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            content=content,
            request=request,
        )

    with HttpFetcher(settings(), transport=httpx.MockTransport(handler)) as fetcher:
        adapter = NewsFirstAdapter(
            fetcher,
            listing_url=LISTING_URL,
            request_delay_seconds=3,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
        candidate = adapter.discover_recent()[0]
        normalized = adapter.normalize(adapter.extract_article(candidate))

    assert clock.sleeps == [3]
    assert normalized.title == "Fixture Ocean Story"


def test_retries_429_using_retry_after_header(
    caplog: pytest.LogCaptureFixture,
) -> None:
    article = (FIXTURES / "newsfirst-article.html").read_bytes()
    clock = FakeClock()
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, request=request)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            content=article,
            request=request,
        )

    caplog.set_level("INFO", logger="ingestion.sources.newsfirst")
    with HttpFetcher(settings(), transport=httpx.MockTransport(handler)) as fetcher:
        adapter = NewsFirstAdapter(
            fetcher,
            listing_url=LISTING_URL,
            request_delay_seconds=3,
            max_retries=1,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            jitter=lambda _start, _end: 0,
        )
        normalized = adapter.normalize(adapter.extract_article(reference()))

    assert attempts == 2
    assert clock.sleeps == [7]
    assert normalized.title == "Fixture Ocean Story"
    assert "newsfirst_rate_limited" in caplog.text
    assert "retry_after_seconds=7.000" in caplog.text
    assert "newsfirst_article_fetch_retried" in caplog.text


def test_429_without_retry_after_uses_bounded_exponential_backoff() -> None:
    article = (FIXTURES / "newsfirst-article.html").read_bytes()
    clock = FakeClock()
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            return httpx.Response(429, request=request)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            content=article,
            request=request,
        )

    with HttpFetcher(settings(), transport=httpx.MockTransport(handler)) as fetcher:
        adapter = NewsFirstAdapter(
            fetcher,
            listing_url=LISTING_URL,
            request_delay_seconds=0,
            max_retries=2,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            jitter=lambda _start, _end: 0,
        )
        normalized = adapter.normalize(adapter.extract_article(reference()))

    assert attempts == 3
    assert clock.sleeps == [2, 4]
    assert normalized.title == "Fixture Ocean Story"


def test_429_retries_stop_after_configured_maximum() -> None:
    clock = FakeClock()
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, request=request)

    with HttpFetcher(settings(), transport=httpx.MockTransport(handler)) as fetcher:
        adapter = NewsFirstAdapter(
            fetcher,
            listing_url=LISTING_URL,
            request_delay_seconds=0,
            max_retries=2,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            jitter=lambda _start, _end: 0,
        )
        with pytest.raises(HttpStatusError) as captured:
            adapter.extract_article(reference())

    assert captured.value.status_code == 429
    assert attempts == 3
    assert clock.sleeps == [2, 4]

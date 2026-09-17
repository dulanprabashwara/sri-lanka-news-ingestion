import httpx
import pytest
from pydantic import SecretStr

from ingestion.config import Settings
from ingestion.http import (
    HttpFetcher,
    HttpStatusError,
    InvalidContentTypeError,
    InvalidFetchUrlError,
    RequestTimeoutError,
)


def settings() -> Settings:
    return Settings(
        http_timeout_seconds=2,
        http_max_redirects=2,
        http_user_agent="SriLankaNewsIngestion/Test",
        api_key=SecretStr("test-secret"),
    )


def test_fetches_text_with_user_agent_and_follows_bounded_redirects() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={"Location": "/article"})
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            text="<h1>Fixture</h1>",
        )

    with HttpFetcher(settings(), transport=httpx.MockTransport(handler)) as fetcher:
        response = fetcher.fetch(
            "https://news.example.com/redirect",
            accepted_content_types={"text/html"},
        )

    assert response.final_url == "https://news.example.com/article"
    assert response.text == "<h1>Fixture</h1>"
    assert len(requests) == 2
    assert requests[0].headers["user-agent"] == "SriLankaNewsIngestion/Test"


def test_maps_non_success_status_to_domain_error() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(503, headers={"Retry-After": "7"})
    )
    with (
        HttpFetcher(settings(), transport=transport) as fetcher,
        pytest.raises(HttpStatusError) as captured,
    ):
        fetcher.fetch("https://news.example.com/feed")
    assert captured.value.status_code == 503
    assert captured.value.headers["retry-after"] == "7"


def test_maps_timeout_to_domain_error() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("fixture timeout", request=request)

    with (
        HttpFetcher(settings(), transport=httpx.MockTransport(timeout)) as fetcher,
        pytest.raises(RequestTimeoutError),
    ):
        fetcher.fetch("https://news.example.com/feed")


def test_rejects_unexpected_content_type() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            headers={"Content-Type": "application/pdf"},
            content=b"fixture",
        )
    )
    with (
        HttpFetcher(settings(), transport=transport) as fetcher,
        pytest.raises(InvalidContentTypeError),
    ):
        fetcher.fetch(
            "https://news.example.com/article",
            accepted_content_types={"text/html"},
        )


def test_rejects_invalid_url_before_transport() -> None:
    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("transport should not be called")

    with (
        HttpFetcher(settings(), transport=httpx.MockTransport(unexpected_request)) as fetcher,
        pytest.raises(InvalidFetchUrlError),
    ):
        fetcher.fetch("file:///local/article.html")

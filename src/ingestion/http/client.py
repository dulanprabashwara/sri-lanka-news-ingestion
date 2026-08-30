from collections.abc import Collection
from dataclasses import dataclass
from types import TracebackType
from urllib.parse import urlsplit

import httpx

from ingestion.config import Settings
from ingestion.http.errors import (
    HttpStatusError,
    InvalidContentTypeError,
    InvalidFetchUrlError,
    NetworkError,
    RequestTimeoutError,
)


@dataclass(frozen=True, slots=True)
class FetchResponse:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    text: str
    content: bytes


class HttpFetcher:
    """Bounded synchronous HTTP client shared by future source adapters."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            timeout=httpx.Timeout(settings.http_timeout_seconds),
            headers={"User-Agent": settings.http_user_agent},
            follow_redirects=True,
            max_redirects=settings.http_max_redirects,
            transport=transport,
        )

    def __enter__(self) -> "HttpFetcher":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def fetch(
        self,
        url: str,
        *,
        accepted_content_types: Collection[str] | None = None,
    ) -> FetchResponse:
        self._validate_url(url)
        try:
            response = self._client.get(url)
        except httpx.TimeoutException as error:
            raise RequestTimeoutError(f"Request timed out for {url}") from error
        except (httpx.NetworkError, httpx.TooManyRedirects) as error:
            raise NetworkError(f"Network request failed for {url}: {error}") from error

        final_url = str(response.url)
        if response.is_error:
            raise HttpStatusError(response.status_code, final_url)

        content_type = response.headers.get("content-type", "").partition(";")[0].strip().casefold()
        if accepted_content_types is not None:
            accepted = {item.casefold() for item in accepted_content_types}
            if content_type not in accepted:
                raise InvalidContentTypeError(content_type, final_url)

        return FetchResponse(
            requested_url=url,
            final_url=final_url,
            status_code=response.status_code,
            content_type=content_type,
            text=response.text,
            content=response.content,
        )

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            raise InvalidFetchUrlError("Fetch URL must be an absolute HTTP or HTTPS URL")
        if parsed.username is not None or parsed.password is not None:
            raise InvalidFetchUrlError("Fetch URL must not contain credentials")

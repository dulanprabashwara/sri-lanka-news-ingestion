class FetchError(RuntimeError):
    """Base error for expected HTTP fetching failures."""


class InvalidFetchUrlError(FetchError):
    """Raised before a request when a URL is not fetchable over HTTP(S)."""


class RequestTimeoutError(FetchError):
    """Raised when a request exceeds the configured timeout."""


class NetworkError(FetchError):
    """Raised for transport failures such as DNS or connection errors."""


class HttpStatusError(FetchError):
    def __init__(self, status_code: int, url: str) -> None:
        super().__init__(f"HTTP {status_code} returned for {url}")
        self.status_code = status_code
        self.url = url


class InvalidContentTypeError(FetchError):
    def __init__(self, content_type: str, url: str) -> None:
        super().__init__(f"Unexpected content type {content_type!r} for {url}")
        self.content_type = content_type
        self.url = url

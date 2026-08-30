from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

_TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
}


class UrlNormalizationError(ValueError):
    """Raised when an article URL cannot be normalized safely."""


def _is_tracking_parameter(name: str) -> bool:
    lowered = name.casefold()
    return lowered.startswith("utm_") or lowered in _TRACKING_PARAMETERS


def canonicalize_url(url: str, *, base_url: str | None = None) -> str:
    """Apply conservative URL canonicalization suitable for article identity."""

    candidate = urljoin(base_url, url) if base_url else url
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as error:
        raise UrlNormalizationError("URL contains an invalid port") from error

    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"}:
        raise UrlNormalizationError("URL must use HTTP or HTTPS")
    if not parsed.hostname:
        raise UrlNormalizationError("URL must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise UrlNormalizationError("Article URLs must not contain credentials")

    hostname = parsed.hostname.casefold()
    rendered_host = f"[{hostname}]" if ":" in hostname else hostname
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = rendered_host if port is None or default_port else f"{rendered_host}:{port}"

    query_items = [
        (name, value)
        for name, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_parameter(name)
    ]

    return urlunsplit(
        (
            scheme,
            netloc,
            parsed.path,
            urlencode(query_items, doseq=True),
            "",
        )
    )

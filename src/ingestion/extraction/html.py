from bs4 import BeautifulSoup, Tag

from ingestion.normalization import UrlNormalizationError, canonicalize_url


class HtmlExtractionError(ValueError):
    """Raised when an expected HTML element or value is unavailable."""


def parse_html(html: str | bytes) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def extract_text(
    document: BeautifulSoup | Tag,
    selector: str,
    *,
    required: bool = True,
    separator: str = " ",
) -> str | None:
    element = document.select_one(selector)
    if element is None:
        if required:
            raise HtmlExtractionError(f"Required selector not found: {selector}")
        return None
    value = " ".join(element.get_text(separator=separator, strip=True).split())
    if not value:
        if required:
            raise HtmlExtractionError(f"Selector contained no text: {selector}")
        return None
    return value


def extract_texts(
    document: BeautifulSoup | Tag,
    selector: str,
    *,
    separator: str = " ",
) -> tuple[str, ...]:
    return tuple(
        normalized
        for element in document.select(selector)
        if (text := element.get_text(separator=separator, strip=True))
        if (normalized := " ".join(text.split()))
    )


def extract_attribute(
    document: BeautifulSoup | Tag,
    selector: str,
    attribute: str,
    *,
    required: bool = True,
) -> str | None:
    element = document.select_one(selector)
    value = element.get(attribute) if element is not None else None
    if isinstance(value, list):
        value = " ".join(value)
    if not isinstance(value, str) or not value.strip():
        if required:
            raise HtmlExtractionError(
                f"Required attribute {attribute!r} not found for selector: {selector}"
            )
        return None
    return value.strip()


def extract_canonical_url(document: BeautifulSoup | Tag, *, page_url: str) -> str:
    href = extract_attribute(document, "link[rel~='canonical']", "href")
    assert href is not None
    try:
        return canonicalize_url(href, base_url=page_url)
    except UrlNormalizationError as error:
        raise HtmlExtractionError("Canonical link is not a valid HTTP(S) URL") from error

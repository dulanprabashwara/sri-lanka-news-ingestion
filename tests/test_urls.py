import pytest

from ingestion.normalization import UrlNormalizationError, canonicalize_url


def test_removes_known_tracking_parameters_and_fragments() -> None:
    result = canonicalize_url(
        "HTTPS://News.Example.COM:443/story?id=7&utm_source=rss&fbclid=abc#comments"
    )
    assert result == "https://news.example.com/story?id=7"


def test_preserves_non_tracking_parameters_order_and_blank_values() -> None:
    result = canonicalize_url("https://example.com/story?edition=lk&preview=&edition=en")
    assert result == "https://example.com/story?edition=lk&preview=&edition=en"


def test_resolves_relative_urls_against_an_explicit_base() -> None:
    result = canonicalize_url("../news/story", base_url="https://example.com/feeds/latest.xml")
    assert result == "https://example.com/news/story"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "/relative/without/base",
        "https://user:secret@example.com/story",
        "https://example.com:invalid/story",
    ],
)
def test_rejects_unsafe_or_incomplete_urls(url: str) -> None:
    with pytest.raises(UrlNormalizationError):
        canonicalize_url(url)

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from ingestion.extraction import (
    HtmlExtractionError,
    extract_attribute,
    extract_canonical_url,
    extract_text,
    extract_texts,
    parse_html,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def document() -> BeautifulSoup:
    return parse_html((FIXTURES / "sample-article.html").read_bytes())


def test_extracts_common_text_without_defining_a_generic_article_parser(
    document: BeautifulSoup,
) -> None:
    assert extract_text(document, "article h1") == "Fixture headline"
    assert extract_texts(document, ".story-body p") == (
        "First paragraph with important detail.",
        "Second paragraph.",
    )
    assert extract_texts(document, ".author") == ("Reporter One", "Reporter Two")


def test_extracts_attributes_and_resolves_canonical_links(document: BeautifulSoup) -> None:
    assert (
        extract_attribute(document, "meta[property='og:image']", "content")
        == "https://cdn.example.com/fixture.jpg"
    )
    assert (
        extract_canonical_url(document, page_url="https://news.example.com/original")
        == "https://news.example.com/news/fixture-story"
    )


def test_supports_optional_and_required_selectors(document: BeautifulSoup) -> None:
    assert extract_text(document, ".missing", required=False) is None
    with pytest.raises(HtmlExtractionError, match="Required selector"):
        extract_text(document, ".missing")

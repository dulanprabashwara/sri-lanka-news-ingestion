"""Reusable RSS and HTML extraction helpers."""

from ingestion.extraction.html import (
    HtmlExtractionError,
    extract_attribute,
    extract_canonical_url,
    extract_text,
    extract_texts,
    parse_html,
)
from ingestion.extraction.rss import RssParseError, parse_feed

__all__ = [
    "HtmlExtractionError",
    "RssParseError",
    "extract_attribute",
    "extract_canonical_url",
    "extract_text",
    "extract_texts",
    "parse_feed",
    "parse_html",
]

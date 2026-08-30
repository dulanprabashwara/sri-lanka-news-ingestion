from datetime import UTC, datetime
from pathlib import Path

import pytest

from ingestion.extraction import RssParseError, parse_feed

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_and_deduplicates_discovery_candidates() -> None:
    content = (FIXTURES / "sample-feed.xml").read_bytes()
    discovered_at = datetime(2026, 8, 30, 7, 0, tzinfo=UTC)

    candidates = parse_feed(
        content,
        source_slug="fixture-news",
        discovered_at=discovered_at,
        base_url="https://news.example.com/rss/latest.xml",
    )

    assert len(candidates) == 2
    assert str(candidates[0].url) == "https://news.example.com/articles/first?story=1"
    assert candidates[0].title == "First fixture headline"
    assert candidates[0].external_id == "fixture-1"
    assert candidates[0].published_at == datetime(2026, 8, 30, 5, 30, tzinfo=UTC)
    assert str(candidates[1].url) == "https://news.example.com/articles/second"
    assert candidates[1].discovered_at == discovered_at


def test_rejects_feed_without_usable_entries() -> None:
    content = (FIXTURES / "malformed-feed.xml").read_bytes()

    with pytest.raises(RssParseError, match="no usable entries"):
        parse_feed(
            content,
            source_slug="fixture-news",
            discovered_at=datetime.now(UTC),
        )

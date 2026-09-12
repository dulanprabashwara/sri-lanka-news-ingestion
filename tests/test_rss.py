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


def test_parses_feed_with_rich_content_description_and_image() -> None:
    xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Daily Mirror News</title>
    <link>https://www.dailymirror.lk/</link>
    <item>
      <title>CPC keeps fuel prices steady</title>
      <link>https://www.dailymirror.lk/breaking-news/CPC-keeps-fuel-prices-steady/108-999</link>
      <guid>cpc-1</guid>
      <pubDate>Sun, 30 Aug 2026 05:30:00 GMT</pubDate>
      <description><![CDATA[<img src="https://cdn.example.com/cpc-fuel.jpg" />The Ceylon Petroleum Corporation has decided to keep fuel prices unchanged. Continue Reading]]></description>
      <content:encoded><![CDATA[<p>The Ceylon Petroleum Corporation has decided to keep fuel prices unchanged.</p><p>Officials stated the formula was reviewed on Saturday.</p>]]></content:encoded>
    </item>
  </channel>
</rss>
"""
    discovered_at = datetime(2026, 8, 30, 7, 0, tzinfo=UTC)
    candidates = parse_feed(
        xml_content,
        source_slug="daily-mirror",
        discovered_at=discovered_at,
        base_url="https://www.dailymirror.lk/rss",
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.title == "CPC keeps fuel prices steady"
    assert candidate.description == "The Ceylon Petroleum Corporation has decided to keep fuel prices unchanged."
    assert candidate.content == (
        "The Ceylon Petroleum Corporation has decided to keep fuel prices unchanged.\n\n"
        "Officials stated the formula was reviewed on Saturday."
    )
    assert candidate.image_url is not None
    assert str(candidate.image_url) == "https://cdn.example.com/cpc-fuel.jpg"

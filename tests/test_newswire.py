from datetime import UTC, datetime

import httpx

from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.models import DiscoveryCandidate
from ingestion.sources import NewswireAdapter

FEED_URL = "https://www.newswire.lk/feed/"
ARTICLE_URL = "https://www.newswire.lk/2026/09/08/test-newswire-article/"

FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Newswire</title>
    <link>https://www.newswire.lk</link>
    <item>
      <title>Test Newswire Article Title</title>
      <link>https://www.newswire.lk/2026/09/08/test-newswire-article/</link>
      <pubDate>Tue, 08 Sep 2026 12:00:00 +0000</pubDate>
      <description><![CDATA[<p><img src="https://www.newswire.lk/wp-content/uploads/2026/09/test.jpg" />Test description summary.</p>]]></description>
    </item>
  </channel>
</rss>
"""

ARTICLE_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Test Newswire Article Title - Newswire</title>
  <link rel="canonical" href="https://www.newswire.lk/2026/09/08/test-newswire-article/" />
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    "headline": "Test Newswire Article Title",
    "datePublished": "2026-09-08T12:00:00+00:00",
    "articleBody": "Newswire paragraph 1. Newswire paragraph 2.",
    "author": {"@type": "Person", "name": "Newswire Reporter"}
  }
  </script>
</head>
<body>
  <h1 class="entry-title">Test Newswire Article Title</h1>
  <div class="entry-content">
    <p>Newswire paragraph 1.</p>
    <p>Newswire paragraph 2.</p>
  </div>
</body>
</html>
"""


def settings() -> Settings:
    return Settings.model_validate(
        {
            "api_key": "test-secret",
            "http_user_agent": "SriLankaNewsIngestion/Test",
        }
    )


def test_discovers_newswire_articles_from_rss() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "application/rss+xml; charset=UTF-8"},
            content=FEED_XML.encode("utf-8"),
            request=request,
        )
    )
    discovered_at = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)

    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = NewswireAdapter(
            fetcher,
            feed_url=FEED_URL,
            now=lambda: discovered_at,
        )
        candidates = adapter.discover_recent()

    assert len(candidates) == 1
    assert str(candidates[0].url) == ARTICLE_URL
    assert candidates[0].title == "Test Newswire Article Title"
    assert candidates[0].discovered_at == discovered_at


def test_extracts_newswire_article_body() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            content=ARTICLE_HTML.encode("utf-8"),
            request=request,
        )
    )
    discovered_at = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)

    with HttpFetcher(settings(), transport=transport) as fetcher:
        adapter = NewswireAdapter(fetcher, feed_url=FEED_URL)
        reference = DiscoveryCandidate.model_validate(
            {
                "source_slug": "newswire",
                "url": ARTICLE_URL,
                "discovered_at": discovered_at,
            }
        )
        normalized = adapter.normalize(adapter.extract_article(reference))

    assert normalized.title == "Test Newswire Article Title"
    assert normalized.authors == ("Newswire Reporter",)
    assert normalized.published_at == datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    assert str(normalized.canonical_url) == ARTICLE_URL
    assert normalized.original_language.value == "en"
    assert normalized.article_text == "Newswire paragraph 1. Newswire paragraph 2."

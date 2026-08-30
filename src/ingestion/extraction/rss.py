import calendar
from datetime import UTC, datetime
from time import struct_time
from typing import Any

import feedparser
from pydantic import ValidationError

from ingestion.models import DiscoveryCandidate
from ingestion.normalization import UrlNormalizationError, canonicalize_url


class RssParseError(ValueError):
    """Raised when a feed cannot provide any usable discovery entries."""


def _entry_datetime(value: Any) -> datetime | None:
    if not isinstance(value, struct_time):
        return None
    return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)


def parse_feed(
    content: str | bytes,
    *,
    source_slug: str,
    discovered_at: datetime,
    base_url: str | None = None,
) -> tuple[DiscoveryCandidate, ...]:
    """Parse valid RSS/Atom entries without applying publisher-specific rules."""

    parsed = feedparser.parse(content)
    candidates: list[DiscoveryCandidate] = []
    seen_urls: set[str] = set()

    for entry in parsed.entries:
        raw_url = entry.get("link")
        if not isinstance(raw_url, str) or not raw_url.strip():
            continue
        try:
            url = canonicalize_url(raw_url, base_url=base_url)
        except UrlNormalizationError:
            continue
        if url in seen_urls:
            continue

        raw_title = entry.get("title")
        title = raw_title.strip() if isinstance(raw_title, str) and raw_title.strip() else None
        raw_external_id = entry.get("id") or entry.get("guid")
        external_id = (
            raw_external_id.strip()
            if isinstance(raw_external_id, str) and raw_external_id.strip()
            else None
        )
        published_at = _entry_datetime(entry.get("published_parsed") or entry.get("updated_parsed"))

        try:
            candidate = DiscoveryCandidate.model_validate(
                {
                    "source_slug": source_slug,
                    "url": url,
                    "discovered_at": discovered_at,
                    "title": title,
                    "published_at": published_at,
                    "external_id": external_id,
                }
            )
        except ValidationError:
            continue
        seen_urls.add(url)
        candidates.append(candidate)

    if not candidates:
        detail = str(parsed.bozo_exception) if parsed.bozo and parsed.bozo_exception else ""
        raise RssParseError(f"Feed contained no usable entries. {detail}".strip())
    return tuple(candidates)

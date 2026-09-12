import calendar
import html
import re
from datetime import UTC, datetime, tzinfo
from email.utils import parsedate_to_datetime
from time import struct_time
from typing import Any

from bs4 import BeautifulSoup
import feedparser
from pydantic import ValidationError

from ingestion.models import DiscoveryCandidate
from ingestion.normalization import UrlNormalizationError, canonicalize_url


class RssParseError(ValueError):
    """Raised when a feed cannot provide any usable discovery entries."""


def _raw_entry_datetime(value: Any, default_timezone: tzinfo | None) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw_value = value.strip()
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw_value)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        if default_timezone is None:
            return None
        parsed = parsed.replace(tzinfo=default_timezone)
    return parsed.astimezone(UTC)


def _entry_datetime(
    value: Any,
    *,
    raw_value: Any,
    default_timezone: tzinfo | None,
) -> datetime | None:
    parsed_raw = _raw_entry_datetime(raw_value, default_timezone)
    if parsed_raw is not None:
        return parsed_raw
    if not isinstance(value, struct_time):
        return None
    return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)


def _clean_rss_description(raw_description: Any, title: str | None) -> tuple[str | None, str | None]:
    if not isinstance(raw_description, str) or not raw_description.strip():
        return None, None
    soup = BeautifulSoup(raw_description, "html.parser")
    img = soup.find("img")
    img_url = img.get("src") if img and img.get("src") else None
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    text = html.unescape(" ".join(soup.get_text().split())).strip()
    text = re.sub(r"(?i)\bcontinue\s*reading\b.*", "", text).strip()
    text = re.sub(r"(?i)throughcontinue.*", "through", text).strip()
    if not text or (title and text.casefold() == title.casefold()):
        return None, img_url
    if len(text) > 2000:
        text = text[:1997] + "..."
    return text, img_url


def _clean_rss_content(raw_content: Any, title: str | None) -> str | None:
    if not isinstance(raw_content, str) or not raw_content.strip():
        return None
    soup = BeautifulSoup(raw_content, "html.parser")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    paragraphs: list[str] = []
    for block in soup.find_all(["p", "div"]):
        para = html.unescape(" ".join(block.get_text().split())).strip()
        para = re.sub(r"(?i)\bcontinue\s*reading\b.*", "", para).strip()
        if para and (not title or para.casefold() != title.casefold()) and para not in paragraphs:
            paragraphs.append(para)
    if not paragraphs:
        text = html.unescape(" ".join(soup.get_text().split())).strip()
        text = re.sub(r"(?i)\bcontinue\s*reading\b.*", "", text).strip()
        if text and (not title or text.casefold() != title.casefold()):
            paragraphs = [text]
    return "\n\n".join(paragraphs) if paragraphs else None


def _extract_rss_image(entry: Any, extracted_img_url: str | None, base_url: str | None) -> str | None:
    candidate_urls: list[str] = []
    if isinstance(extracted_img_url, str) and extracted_img_url.strip():
        candidate_urls.append(extracted_img_url.strip())
    href = entry.get("href")
    if isinstance(href, str) and href.strip():
        candidate_urls.append(href.strip())
    media_content = entry.get("media_content")
    if isinstance(media_content, list):
        for item in media_content:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                candidate_urls.append(item["url"].strip())
    enclosures = entry.get("enclosures")
    if isinstance(enclosures, list):
        for item in enclosures:
            if isinstance(item, dict) and isinstance(item.get("href"), str):
                candidate_urls.append(item["href"].strip())

    for url_candidate in candidate_urls:
        try:
            return canonicalize_url(url_candidate, base_url=base_url)
        except UrlNormalizationError:
            continue
    return None


def parse_feed(
    content: str | bytes,
    *,
    source_slug: str,
    discovered_at: datetime,
    base_url: str | None = None,
    default_timezone: tzinfo | None = None,
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
        parsed_datetime = entry.get("published_parsed")
        if parsed_datetime is None and "updated_parsed" in entry:
            parsed_datetime = entry["updated_parsed"]
        published_at = _entry_datetime(
            parsed_datetime,
            raw_value=entry.get("published") or entry.get("updated"),
            default_timezone=default_timezone,
        )

        raw_description = entry.get("summary") or entry.get("description")
        description, img_from_desc = _clean_rss_description(raw_description, title)

        raw_content = None
        content_list = entry.get("content")
        if isinstance(content_list, list) and content_list:
            first = content_list[0]
            if isinstance(first, dict):
                raw_content = first.get("value")
        if not raw_content:
            raw_content = entry.get("content_encoded")
        content_text = _clean_rss_content(raw_content, title)

        image_url = _extract_rss_image(entry, img_from_desc, base_url=base_url)

        try:
            candidate = DiscoveryCandidate.model_validate(
                {
                    "source_slug": source_slug,
                    "url": url,
                    "discovered_at": discovered_at,
                    "title": title,
                    "published_at": published_at,
                    "external_id": external_id,
                    "description": description,
                    "content": content_text,
                    "image_url": image_url,
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

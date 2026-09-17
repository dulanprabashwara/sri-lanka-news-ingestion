import html
import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, ClassVar
from urllib.parse import urlsplit, urlunsplit

import feedparser
from bs4 import BeautifulSoup, Tag
from pydantic import ValidationError

from ingestion.extraction import extract_texts, parse_feed, parse_html
from ingestion.http import FetchError, FetchResponse, HttpFetcher
from ingestion.models import (
    ArticleCategory,
    DiscoveryCandidate,
    ExtractedArticle,
    ImageMetadata,
    Language,
    NormalizedArticle,
)
from ingestion.normalization import UrlNormalizationError, canonicalize_url
from ingestion.sources.base import PublisherExtractionError, SourceAdapter
from ingestion.sources.common import article_summary, image_metadata

logger = logging.getLogger(__name__)


class LakbimaNewsExtractionError(PublisherExtractionError):
    """Raised when Lakbima data cannot form a valid article."""


@dataclass(frozen=True, slots=True)
class _FeedMetadata:
    authors: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    image_url: str | None = None


class LakbimaNewsAdapter(SourceAdapter):
    SOURCE_SLUG = "lakbima-news"
    SOURCE_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="Asia/Colombo")
    ACCEPTED_FEED_TYPES: ClassVar[frozenset[str]] = frozenset(
        {"application/rss+xml", "application/xml", "text/xml", "text/html"}
    )
    TITLE_SELECTORS = ("article h1.entry-title", "h1.entry-title", "article h1", "main h1")
    BODY_SELECTORS = ("article .entry-content > p", ".entry-content > p")
    INVALID_TITLES: ClassVar[frozenset[str]] = frozenset(
        {"lakbima news", "access denied", "forbidden", "just a moment...", "server error"}
    )
    CHALLENGE_MARKERS: ClassVar[tuple[str, ...]] = (
        "checking your browser",
        "cf-chl-",
        "captcha",
        "access denied",
        "you have been blocked",
    )
    MIN_FEED_BODY_CHARACTERS = 200
    MIN_FEED_BODY_WORDS = 30
    CATEGORY_MAP: ClassVar[dict[str, ArticleCategory]] = {
        "latest news": ArticleCategory.LOCAL,
        "local": ArticleCategory.LOCAL,
        "politics": ArticleCategory.POLITICS,
        "business": ArticleCategory.BUSINESS,
        "sports": ArticleCategory.SPORTS,
        "world": ArticleCategory.WORLD,
        "technology": ArticleCategory.TECHNOLOGY,
        "health": ArticleCategory.HEALTH,
        "entertainment": ArticleCategory.ENTERTAINMENT,
    }

    def __init__(
        self,
        fetcher: HttpFetcher,
        *,
        feed_url: str,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._feed_url = feed_url
        self._now = now or (lambda: datetime.now(UTC))
        self._feed_metadata: dict[str, _FeedMetadata] = {}

    @property
    def source_slug(self) -> str:
        return self.SOURCE_SLUG

    def discover_recent(self) -> Sequence[DiscoveryCandidate]:
        response = self._fetcher.fetch(
            self._feed_url, accepted_content_types=self.ACCEPTED_FEED_TYPES
        )
        candidates = parse_feed(
            response.content,
            source_slug=self.source_slug,
            discovered_at=self._now(),
            base_url=response.final_url,
            default_timezone=self.SOURCE_TIMEZONE,
        )
        self._feed_metadata = self._extract_feed_metadata(
            response.content, base_url=response.final_url
        )
        normalized: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for candidate in candidates:
            try:
                canonical_url = self._canonical_article_url(str(candidate.url))
            except UrlNormalizationError:
                continue
            if canonical_url in seen or not self._is_article_url(canonical_url):
                continue
            metadata = self._feed_metadata.get(canonical_url, _FeedMetadata())
            values = candidate.model_dump()
            values["url"] = canonical_url
            if candidate.image_url is None and metadata.image_url is not None:
                values["image_url"] = metadata.image_url
            normalized.append(DiscoveryCandidate.model_validate(values))
            seen.add(canonical_url)
        return tuple(normalized)

    def extract_article(self, candidate: DiscoveryCandidate) -> ExtractedArticle:
        request_url = self._canonical_article_url(str(candidate.url))
        try:
            response = self._fetcher.fetch(request_url, accepted_content_types={"text/html"})
        except FetchError as error:
            fetch_reason = type(error).__name__
            logger.warning(
                "lakbima_detail_unavailable source=%s canonical_url=%s reason=%s",
                self.source_slug,
                request_url,
                fetch_reason,
            )
            return self._feed_fallback(candidate, request_url, fetch_reason)

        challenge_reason = self._challenge_reason(response)
        if challenge_reason is not None:
            logger.warning(
                "lakbima_detail_unavailable source=%s canonical_url=%s reason=%s",
                self.source_slug,
                request_url,
                challenge_reason,
            )
            return self._feed_fallback(candidate, request_url, challenge_reason)

        document = parse_html(response.text)
        data = self._news_article_data(document)
        metadata = self._metadata_for(candidate)
        title = self._title(document, data, candidate)
        return self._article(
            candidate,
            title=title,
            body=self._body(document, data, title),
            original_url=request_url,
            canonical_url=self._canonical_url(document, data, response.final_url),
            published_at=self._published_at(document, data, candidate),
            authors=self._authors(document, data) or metadata.authors,
            summary=article_summary(document, data) or self._summary(candidate),
            category=self._category(metadata.categories),
            image=(
                image_metadata(document, data, response.final_url)
                or self._page_image(document, response.final_url)
                or self._feed_image(candidate)
            ),
        )

    def normalize(self, article: ExtractedArticle) -> NormalizedArticle:
        return NormalizedArticle.model_validate(article.model_dump())

    def _feed_fallback(
        self, candidate: DiscoveryCandidate, canonical_url: str, reason: str
    ) -> ExtractedArticle:
        title = self._normalize_title(candidate.title or "")
        body = self._fallback_body(candidate.content, title)
        if title is None or body is None or candidate.published_at is None:
            logger.warning(
                "lakbima_fallback_unusable source=%s canonical_url=%s reason=%s",
                self.source_slug,
                canonical_url,
                reason,
            )
            raise LakbimaNewsExtractionError(
                "Lakbima feed fallback lacks a valid title, publication time, or substantial content."
            )
        metadata = self._metadata_for(candidate)
        article = self._article(
            candidate,
            title=title,
            body=body,
            original_url=canonical_url,
            canonical_url=canonical_url,
            published_at=candidate.published_at,
            authors=metadata.authors,
            summary=self._summary(candidate),
            category=self._category(metadata.categories),
            image=self._feed_image(candidate),
        )
        logger.info(
            "lakbima_feed_fallback_used source=%s canonical_url=%s reason=%s",
            self.source_slug,
            canonical_url,
            reason,
        )
        return article

    def _article(self, candidate: DiscoveryCandidate, **values: Any) -> ExtractedArticle:
        try:
            return ExtractedArticle.model_validate(
                {
                    "source_slug": self.source_slug,
                    "original_language": Language.SINHALA,
                    "discovered_at": candidate.discovered_at,
                    "article_text": values.pop("body"),
                    **values,
                }
            )
        except ValidationError as error:
            raise LakbimaNewsExtractionError("Lakbima article data is invalid.") from error

    def _title(
        self, document: BeautifulSoup, data: dict[str, Any], candidate: DiscoveryCandidate
    ) -> str:
        headline = data.get("headline")
        if isinstance(headline, str) and (title := self._normalize_title(headline)):
            return title
        for selector in self.TITLE_SELECTORS:
            element = document.select_one(selector)
            if element is not None and (
                title := self._normalize_title(element.get_text(" ", strip=True))
            ):
                return title
        og = document.select_one("meta[property='og:title']")
        if (
            og is not None
            and isinstance(og.get("content"), str)
            and (title := self._normalize_title(str(og.get("content"))))
        ):
            return title
        if title := self._normalize_title(candidate.title or ""):
            return title
        raise LakbimaNewsExtractionError("Lakbima article title is missing.")

    def _body(self, document: BeautifulSoup, data: dict[str, Any], title: str) -> str:
        article_body = data.get("articleBody")
        if isinstance(article_body, str) and (body := self._normalize_body(article_body, title)):
            return body
        for selector in self.BODY_SELECTORS:
            body = self._normalize_body("\n\n".join(extract_texts(document, selector)), title)
            if body:
                return body
        raise LakbimaNewsExtractionError("Lakbima article body is missing.")

    def _canonical_url(self, document: BeautifulSoup, data: dict[str, Any], page_url: str) -> str:
        values: list[str] = []
        main_entity = data.get("mainEntityOfPage")
        if isinstance(main_entity, Mapping) and isinstance(main_entity.get("@id"), str):
            values.append(str(main_entity.get("@id")))
        elif isinstance(main_entity, str):
            values.append(main_entity)
        for selector, attribute in (
            ("link[rel~='canonical']", "href"),
            ("meta[property='og:url']", "content"),
        ):
            element = document.select_one(selector)
            value = element.get(attribute) if element is not None else None
            if isinstance(value, str):
                values.append(value)
        values.append(page_url)
        for value in values:
            with suppress(UrlNormalizationError):
                normalized = self._canonical_article_url(value)
                if self._is_article_url(normalized):
                    return normalized
        raise LakbimaNewsExtractionError("Lakbima canonical URL is missing.")

    def _published_at(
        self, document: BeautifulSoup, data: dict[str, Any], candidate: DiscoveryCandidate
    ) -> datetime:
        values: list[str] = []
        value = data.get("datePublished")
        if isinstance(value, str):
            values.append(value)
        element = document.select_one("time[datetime]")
        if element is not None and isinstance(element.get("datetime"), str):
            values.append(str(element.get("datetime")))
        for raw in values:
            with suppress(ValueError):
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    return parsed.astimezone(UTC)
        if candidate.published_at is not None:
            return candidate.published_at
        raise LakbimaNewsExtractionError("Lakbima publication time is missing.")

    def _authors(self, document: BeautifulSoup, data: dict[str, Any]) -> tuple[str, ...]:
        names: list[str] = []
        raw = data.get("author")
        for item in raw if isinstance(raw, list) else [raw]:
            value = item.get("name") if isinstance(item, Mapping) else item
            if isinstance(value, str) and (name := " ".join(value.split())) and name not in names:
                names.append(name)
        for element in document.select(".byline .author, .author.vcard, .url.fn.n"):
            name = " ".join(element.get_text(" ", strip=True).split())
            if name and name not in names:
                names.append(name)
        return tuple(names)

    def _news_article_data(self, document: BeautifulSoup) -> dict[str, Any]:
        for script in document.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                payload = json.loads(script.string or script.get_text())
            except (json.JSONDecodeError, TypeError):
                continue
            items = payload if isinstance(payload, list) else [payload]
            if isinstance(payload, dict) and isinstance(payload.get("@graph"), list):
                items = payload["@graph"]
            for item in items:
                if isinstance(item, dict) and item.get("@type") in {"Article", "NewsArticle"}:
                    return item
        return {}

    def _extract_feed_metadata(self, content: bytes, *, base_url: str) -> dict[str, _FeedMetadata]:
        parsed: Any = feedparser.parse(content)
        result: dict[str, _FeedMetadata] = {}
        for entry in parsed.entries:
            raw_url = entry.get("link")
            if not isinstance(raw_url, str):
                continue
            with suppress(UrlNormalizationError):
                url = self._canonical_article_url(canonicalize_url(raw_url, base_url=base_url))
                author = entry.get("author") or entry.get("dc_creator")
                authors = (
                    (" ".join(author.split()),)
                    if isinstance(author, str) and author.strip()
                    else ()
                )
                categories = tuple(
                    dict.fromkeys(
                        " ".join(str(item.get("term")).split())
                        for item in entry.get("tags", [])
                        if isinstance(item, Mapping) and isinstance(item.get("term"), str)
                    )
                )
                result.setdefault(
                    url,
                    _FeedMetadata(authors, categories, self._entry_image(entry, base_url)),
                )
        return result

    def _entry_image(self, entry: Any, base_url: str) -> str | None:
        candidates: list[str] = []
        for key in ("media_content", "media_thumbnail", "enclosures"):
            items = entry.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, Mapping):
                    value = item.get("url") or item.get("href")
                    if isinstance(value, str):
                        candidates.append(value)
        content = entry.get("content")
        if isinstance(content, list) and content and isinstance(content[0], Mapping):
            markup = content[0].get("value")
            if isinstance(markup, str):
                image = BeautifulSoup(markup, "html.parser").find("img")
                if isinstance(image, Tag) and isinstance(image.get("src"), str):
                    candidates.append(str(image.get("src")))
        for value in candidates:
            with suppress(UrlNormalizationError):
                return canonicalize_url(value, base_url=base_url)
        return None

    def _metadata_for(self, candidate: DiscoveryCandidate) -> _FeedMetadata:
        return self._feed_metadata.get(
            self._canonical_article_url(str(candidate.url)), _FeedMetadata()
        )

    def _feed_image(self, candidate: DiscoveryCandidate) -> ImageMetadata | None:
        url = candidate.image_url or self._metadata_for(candidate).image_url
        if url is None:
            return None
        with suppress(ValidationError):
            return ImageMetadata.model_validate({"url": str(url)})
        return None

    def _page_image(self, document: BeautifulSoup, page_url: str) -> ImageMetadata | None:
        element = document.select_one(
            "article img.wp-post-image, article img.attachment-post-thumbnail"
        )
        value = element.get("src") if element is not None else None
        if isinstance(value, str):
            with suppress(ValidationError, UrlNormalizationError):
                url = canonicalize_url(value, base_url=page_url)
                return ImageMetadata.model_validate({"url": url})
        return None

    def _summary(self, candidate: DiscoveryCandidate) -> str | None:
        value = " ".join(html.unescape(candidate.description or "").split()).strip()
        value = re.sub(r"(?i)\bcontinue\s*reading\b.*", "", value).strip()
        return value[:2000] if value else None

    def _fallback_body(self, value: str | None, title: str | None) -> str | None:
        body = self._normalize_body(value or "", title)
        if (
            len(body) < self.MIN_FEED_BODY_CHARACTERS
            or len(body.split()) < self.MIN_FEED_BODY_WORDS
        ):
            return None
        return body

    @classmethod
    def _normalize_body(cls, value: str, title: str | None) -> str:
        paragraphs: list[str] = []
        ignored = {"share", title.casefold() if title else ""}
        for raw in value.splitlines():
            paragraph = " ".join(html.unescape(raw).split()).strip()
            paragraph = re.sub(r"(?i)\bcontinue\s*reading\b.*", "", paragraph).strip()
            if paragraph and paragraph.casefold() not in ignored and paragraph not in paragraphs:
                paragraphs.append(paragraph)
        return "\n\n".join(paragraphs)

    @classmethod
    def _normalize_title(cls, value: str) -> str | None:
        title = " ".join(html.unescape(value).split()).strip()
        title = re.sub(
            r"\s+[|\-\u2013\u2014]\s+Lakbima News$", "", title, flags=re.IGNORECASE
        ).strip()
        if (
            not title
            or title.casefold() in cls.INVALID_TITLES
            or not any(char.isalnum() for char in title)
        ):
            return None
        return title[:1000]

    @classmethod
    def _canonical_article_url(cls, value: str) -> str:
        parsed = urlsplit(canonicalize_url(value))
        if (parsed.hostname or "").casefold() in {"lakbima.news", "www.lakbima.news"}:
            path = parsed.path or "/"
            if path != "/" and not path.endswith("/"):
                path += "/"
            return urlunsplit(("https", "lakbima.news", path, parsed.query, ""))
        return urlunsplit(parsed)

    @staticmethod
    def _is_article_url(value: str) -> bool:
        parsed = urlsplit(value)
        return parsed.hostname == "lakbima.news" and parsed.path not in {"", "/", "/feed/"}

    @classmethod
    def _category(cls, categories: tuple[str, ...]) -> ArticleCategory | None:
        return next(
            (
                cls.CATEGORY_MAP[value.casefold()]
                for value in categories
                if value.casefold() in cls.CATEGORY_MAP
            ),
            None,
        )

    def _challenge_reason(self, response: FetchResponse) -> str | None:
        lowered = response.text.casefold()
        return (
            "challenge_page"
            if any(marker in lowered for marker in self.CHALLENGE_MARKERS)
            else None
        )

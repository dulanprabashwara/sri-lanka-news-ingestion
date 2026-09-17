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
from bs4 import BeautifulSoup
from bs4.element import Tag
from pydantic import ValidationError

from ingestion.extraction import (
    HtmlExtractionError,
    extract_canonical_url,
    extract_texts,
    parse_feed,
    parse_html,
)
from ingestion.http import FetchResponse, HttpFetcher, HttpStatusError
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


class TheIslandExtractionError(PublisherExtractionError):
    """Raised when The Island markup lacks required article data."""


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _FeedMetadata:
    authors: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    image_url: str | None = None


class TheIslandAdapter(SourceAdapter):
    SOURCE_SLUG = "the-island"
    SOURCE_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="Asia/Colombo")
    TITLE_SELECTORS = (
        "h1.tdb-title-text",
        "h1.entry-title",
        "article h1",
        "main h1",
    )
    INVALID_TITLES: ClassVar[frozenset[str]] = frozenset(
        {
            "access denied",
            "forbidden",
            "just a moment...",
            "the island",
            "the island newspaper",
            "you are being redirected...",
        }
    )
    SITE_SUFFIX = re.compile(
        r"\s+[|\-\u2013\u2014]\s+(?:the\s+island(?:\s+newspaper)?)$",
        re.IGNORECASE,
    )
    BODY_SELECTORS = (
        "div.tdb-block-inner.td-fix-index > p",
        "div.td-post-content p",
        "#mvp-content-main p",
    )
    AUTHOR_SELECTOR = ".tdb-author-name, .td-post-author-name a"
    ACCEPTED_FEED_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            "application/rss+xml",
            "application/xml",
            "text/xml",
            "text/html",
        }
    )
    ACCESS_RESTRICTED_STATUSES: ClassVar[frozenset[int]] = frozenset({403, 429})
    CHALLENGE_MARKERS: ClassVar[tuple[str, ...]] = (
        "sucuri_cloudproxy_js",
        "javascript is required. please enable javascript before you are allowed",
        "<title>you are being redirected...</title>",
    )
    MIN_FEED_BODY_CHARACTERS = 200
    MIN_FEED_BODY_WORDS = 30
    CATEGORY_MAP: ClassVar[dict[str, ArticleCategory]] = {
        "business": ArticleCategory.BUSINESS,
        "foreign news": ArticleCategory.WORLD,
        "health": ArticleCategory.HEALTH,
        "latest news": ArticleCategory.LOCAL,
        "news": ArticleCategory.LOCAL,
        "politics": ArticleCategory.POLITICS,
        "science": ArticleCategory.SCIENCE,
        "sports": ArticleCategory.SPORTS,
        "tech": ArticleCategory.TECHNOLOGY,
        "technology": ArticleCategory.TECHNOLOGY,
        "weather": ArticleCategory.LOCAL,
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
            self._feed_url,
            accepted_content_types=self.ACCEPTED_FEED_TYPES,
        )
        candidates = parse_feed(
            response.content,
            source_slug=self.source_slug,
            discovered_at=self._now(),
            base_url=response.final_url,
            default_timezone=self.SOURCE_TIMEZONE,
        )
        self._feed_metadata = self._extract_feed_metadata(
            response.content,
            base_url=response.final_url,
        )
        normalized: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for candidate in candidates:
            secure_url = self._canonical_island_url(str(candidate.url))
            if secure_url in seen:
                continue
            metadata = self._feed_metadata.get(secure_url, _FeedMetadata())
            payload = candidate.model_dump()
            payload["url"] = secure_url
            if candidate.image_url is None and metadata.image_url is not None:
                payload["image_url"] = metadata.image_url
            normalized.append(DiscoveryCandidate.model_validate(payload))
            seen.add(secure_url)
            if secure_url != str(candidate.url):
                logger.info(
                    "the_island_https_normalized source=%s canonical_url=%s",
                    self.source_slug,
                    secure_url,
                )
        return tuple(normalized)

    def extract_article(self, candidate: DiscoveryCandidate) -> ExtractedArticle:
        request_url = self._canonical_island_url(str(candidate.url))
        try:
            response = self._fetcher.fetch(
                request_url,
                accepted_content_types={"text/html"},
            )
        except HttpStatusError as error:
            if error.status_code not in self.ACCESS_RESTRICTED_STATUSES:
                raise
            logger.warning(
                "the_island_detail_challenged source=%s canonical_url=%s reason=http_%d",
                self.source_slug,
                request_url,
                error.status_code,
            )
            return self._feed_fallback(
                candidate,
                canonical_url=request_url,
                reason=f"http_{error.status_code}",
            )

        challenge_reason = self._challenge_reason(response)
        if challenge_reason is not None:
            logger.warning(
                "the_island_detail_challenged source=%s canonical_url=%s reason=%s",
                self.source_slug,
                request_url,
                challenge_reason,
            )
            return self._feed_fallback(
                candidate,
                canonical_url=request_url,
                reason=challenge_reason,
            )

        document = parse_html(response.text)
        structured_data = self._news_article_data(document)
        metadata = self._metadata_for(candidate)

        title = self._title(document, structured_data)
        body = self._body(document, structured_data)
        published_at = self._published_at(structured_data, candidate)
        canonical_url = self._canonical_url(document, structured_data, response.final_url)
        authors = self._authors(document, structured_data) or metadata.authors
        summary = article_summary(document, structured_data) or self._fallback_summary(candidate)
        image = image_metadata(document, structured_data, response.final_url)
        if image is None:
            image = self._fallback_image(candidate, canonical_url)

        try:
            return ExtractedArticle.model_validate(
                {
                    "source_slug": self.source_slug,
                    "title": title,
                    "authors": authors,
                    "original_url": request_url,
                    "canonical_url": canonical_url,
                    "original_language": Language.ENGLISH,
                    "published_at": published_at,
                    "discovered_at": candidate.discovered_at,
                    "article_text": body,
                    "summary": summary,
                    "category": self._category(metadata.categories),
                    "image": image,
                }
            )
        except ValidationError as error:
            raise TheIslandExtractionError("The Island article data is invalid.") from error

    def normalize(self, article: ExtractedArticle) -> NormalizedArticle:
        return NormalizedArticle.model_validate(article.model_dump())

    def _feed_fallback(
        self,
        candidate: DiscoveryCandidate,
        *,
        canonical_url: str,
        reason: str,
    ) -> ExtractedArticle:
        title = self._normalize_title(candidate.title or "")
        body = self._fallback_body(candidate.content, title)
        if title is None or body is None or candidate.published_at is None:
            logger.warning(
                "the_island_article_fallback_unusable source=%s canonical_url=%s reason=%s",
                self.source_slug,
                canonical_url,
                reason,
            )
            raise TheIslandExtractionError(
                "The Island feed fallback lacks a valid title, publication time, "
                "or substantial article content."
            )

        metadata = self._metadata_for(candidate)
        try:
            article = ExtractedArticle.model_validate(
                {
                    "source_slug": self.source_slug,
                    "title": title,
                    "authors": metadata.authors,
                    "original_url": canonical_url,
                    "canonical_url": canonical_url,
                    "original_language": Language.ENGLISH,
                    "published_at": candidate.published_at,
                    "discovered_at": candidate.discovered_at,
                    "article_text": body,
                    "summary": self._fallback_summary(candidate),
                    "category": self._category(metadata.categories),
                    "image": self._fallback_image(candidate, canonical_url),
                }
            )
        except ValidationError as error:
            raise TheIslandExtractionError("The Island feed fallback data is invalid.") from error

        logger.info(
            "the_island_feed_fallback_used source=%s canonical_url=%s fallback=feed reason=%s",
            self.source_slug,
            canonical_url,
            reason,
        )
        return article

    def _challenge_reason(self, response: FetchResponse) -> str | None:
        lowered = response.text.casefold()
        if "sucuri_cloudproxy_js" in lowered:
            return "sucuri_challenge"
        if any(marker in lowered for marker in self.CHALLENGE_MARKERS):
            return "javascript_interstitial"
        if 300 <= response.status_code < 400:
            return f"unresolved_redirect_{response.status_code}"
        return None

    def _fallback_body(self, value: str | None, title: str | None) -> str | None:
        if not value:
            return None
        paragraphs: list[str] = []
        for raw_paragraph in value.splitlines():
            paragraph = " ".join(html.unescape(raw_paragraph).split()).strip()
            paragraph = re.sub(r"(?i)\bcontinue\s*reading\b.*", "", paragraph).strip()
            if re.match(r"(?i)^the post .+ appeared first on (?:the )?island\.?$", paragraph):
                continue
            if (
                paragraph
                and (title is None or paragraph.casefold() != title.casefold())
                and paragraph not in paragraphs
            ):
                paragraphs.append(paragraph)
        body = "\n\n".join(paragraphs)
        if self._contains_challenge_marker(body):
            return None
        if (
            len(body) < self.MIN_FEED_BODY_CHARACTERS
            or len(body.split()) < self.MIN_FEED_BODY_WORDS
        ):
            return None
        return body

    def _fallback_summary(self, candidate: DiscoveryCandidate) -> str | None:
        if not candidate.description:
            return None
        summary = " ".join(html.unescape(candidate.description).split()).strip()
        summary = re.sub(r"(?i)\bcontinue\s*reading\b.*", "", summary).strip()
        title = self._normalize_title(candidate.title or "")
        if (
            not summary
            or self._contains_challenge_marker(summary)
            or (title is not None and summary.casefold() == title.casefold())
        ):
            return None
        return summary[:2000]

    def _fallback_image(
        self,
        candidate: DiscoveryCandidate,
        page_url: str,
    ) -> ImageMetadata | None:
        metadata = self._metadata_for(candidate)
        image_url = candidate.image_url or metadata.image_url
        if image_url is None:
            return None
        try:
            return ImageMetadata.model_validate(
                {"url": str(image_url)},
                context={"page_url": page_url},
            )
        except ValidationError:
            return None

    def _extract_feed_metadata(
        self,
        content: bytes,
        *,
        base_url: str,
    ) -> dict[str, _FeedMetadata]:
        parsed: Any = feedparser.parse(content)
        metadata: dict[str, _FeedMetadata] = {}
        for entry in parsed.entries:
            raw_url = entry.get("link")
            if not isinstance(raw_url, str):
                continue
            with suppress(UrlNormalizationError):
                url = self._canonical_island_url(canonicalize_url(raw_url, base_url=base_url))
                if url in metadata:
                    continue
                author = entry.get("author") or entry.get("dc_creator")
                authors = self._author_names(author)
                tags = entry.get("tags")
                categories: list[str] = []
                if isinstance(tags, list):
                    for item in tags:
                        if not isinstance(item, Mapping):
                            continue
                        term = item.get("term")
                        if not isinstance(term, str):
                            continue
                        normalized = " ".join(html.unescape(term).split())
                        if normalized and normalized not in categories:
                            categories.append(normalized)
                metadata[url] = _FeedMetadata(
                    authors=authors,
                    categories=tuple(categories),
                    image_url=self._feed_image(entry, base_url),
                )
        return metadata

    def _feed_image(self, entry: Any, base_url: str) -> str | None:
        candidates: list[str] = []
        for key in ("media_content", "media_thumbnail", "enclosures"):
            items = entry.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                value = item.get("url") or item.get("href")
                if isinstance(value, str):
                    candidates.append(value)

        content_items = entry.get("content")
        raw_content = None
        if isinstance(content_items, list) and content_items:
            first = content_items[0]
            if isinstance(first, Mapping):
                raw_content = first.get("value")
        if isinstance(raw_content, str):
            image = BeautifulSoup(raw_content, "html.parser").find("img")
            source = image.get("src") if isinstance(image, Tag) else None
            if isinstance(source, str):
                candidates.append(source)

        for candidate in candidates:
            with suppress(UrlNormalizationError):
                return self._canonical_island_url(canonicalize_url(candidate, base_url=base_url))
        return None

    def _metadata_for(self, candidate: DiscoveryCandidate) -> _FeedMetadata:
        return self._feed_metadata.get(
            self._canonical_island_url(str(candidate.url)),
            _FeedMetadata(),
        )

    @classmethod
    def _category(cls, categories: tuple[str, ...]) -> ArticleCategory | None:
        for category in categories:
            mapped = cls.CATEGORY_MAP.get(category.casefold())
            if mapped is not None:
                return mapped
        return None

    @classmethod
    def _canonical_island_url(cls, value: str) -> str:
        normalized = canonicalize_url(value)
        parsed = urlsplit(normalized)
        if parsed.scheme == "http" and parsed.hostname in {"island.lk", "www.island.lk"}:
            return urlunsplit(parsed._replace(scheme="https"))
        return normalized

    @classmethod
    def _contains_challenge_marker(cls, value: str) -> bool:
        lowered = value.casefold()
        return any(marker in lowered for marker in cls.CHALLENGE_MARKERS)

    def _news_article_data(self, document: BeautifulSoup) -> dict[str, Any]:
        for script in document.find_all("script", attrs={"type": "application/ld+json"}):
            raw = script.string or script.get_text()
            if not raw.strip():
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            for item in self._structured_items(payload):
                item_type = item.get("@type")
                types = item_type if isinstance(item_type, list) else [item_type]
                if "NewsArticle" in types or "Article" in types:
                    return item
        return {}

    def _structured_items(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        graph = payload.get("@graph")
        if isinstance(graph, list):
            return [item for item in graph if isinstance(item, dict)]
        return [payload]

    def _title(self, document: BeautifulSoup, data: dict[str, Any]) -> str:
        headline = data.get("headline")
        if isinstance(headline, str):
            normalized = self._normalize_title(headline)
            if normalized:
                return normalized

        for selector in self.TITLE_SELECTORS:
            element = document.select_one(selector)
            if element is None:
                continue
            normalized = self._normalize_title(element.get_text(" ", strip=True))
            if normalized:
                return normalized

        open_graph = document.select_one("meta[property='og:title']")
        if open_graph is not None:
            content = open_graph.get("content")
            if isinstance(content, list):
                content = content[0] if content else None
            if isinstance(content, str):
                normalized = self._normalize_title(content)
                if normalized:
                    return normalized

        if document.title is not None:
            normalized = self._normalize_title(document.title.get_text(" ", strip=True))
            if normalized:
                return normalized

        raise TheIslandExtractionError("The Island article title is missing.")

    @classmethod
    def _normalize_title(cls, value: str) -> str | None:
        normalized = " ".join(html.unescape(value).split()).strip()
        normalized = cls.SITE_SUFFIX.sub("", normalized).strip()
        if (
            not normalized
            or len(normalized) > 1_000
            or normalized.casefold() in cls.INVALID_TITLES
            or not any(character.isalnum() for character in normalized)
        ):
            return None
        return normalized

    def _body(self, document: BeautifulSoup, data: dict[str, Any]) -> str:
        article_body = data.get("articleBody")
        if isinstance(article_body, str) and article_body.strip():
            return self._normalize_body(html.unescape(article_body))
        for selector in self.BODY_SELECTORS:
            paragraphs = extract_texts(document, selector)
            if paragraphs:
                return "\n\n".join(paragraphs)
        raise TheIslandExtractionError("The Island article body is missing.")

    def _published_at(
        self,
        data: dict[str, Any],
        candidate: DiscoveryCandidate,
    ) -> datetime:
        raw_date = data.get("datePublished")
        if isinstance(raw_date, str):
            try:
                parsed = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                    return parsed.astimezone(UTC)
            except ValueError:
                pass
        if candidate.published_at is not None:
            return candidate.published_at
        raise TheIslandExtractionError("The Island publication time is missing.")

    def _canonical_url(
        self,
        document: BeautifulSoup,
        data: dict[str, Any],
        page_url: str,
    ) -> str:
        extracted = None
        with suppress(HtmlExtractionError):
            extracted = extract_canonical_url(document, page_url=page_url)

        if extracted is None:
            og_url = document.select_one("meta[property='og:url']")
            content = og_url.get("content") if og_url else None
            if isinstance(content, list):
                content = content[0] if content else None
            if isinstance(content, str):
                with suppress(UrlNormalizationError):
                    extracted = canonicalize_url(content, base_url=page_url)

        if extracted is None:
            structured_url = data.get("url")
            if isinstance(structured_url, str):
                with suppress(UrlNormalizationError):
                    extracted = canonicalize_url(structured_url, base_url=page_url)

        if extracted is None:
            extracted = page_url

        try:
            url = canonicalize_url(extracted, base_url=page_url)
            return self._canonical_island_url(url)
        except UrlNormalizationError as error:
            raise TheIslandExtractionError("The Island canonical URL is missing.") from error

    def _authors(self, document: BeautifulSoup, data: dict[str, Any]) -> tuple[str, ...]:
        names = self._author_names(data.get("author"))
        if names:
            return names
        return extract_texts(document, self.AUTHOR_SELECTOR)

    def _author_names(self, value: Any) -> tuple[str, ...]:
        items = value if isinstance(value, list) else [value]
        names: list[str] = []
        for item in items:
            name = item.get("name") if isinstance(item, dict) else item
            if isinstance(name, str):
                normalized = " ".join(html.unescape(name).split())
                if normalized and normalized not in names:
                    names.append(normalized)
        return tuple(names)

    @staticmethod
    def _normalize_body(value: str) -> str:
        paragraphs = [" ".join(paragraph.split()) for paragraph in value.splitlines()]
        return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)

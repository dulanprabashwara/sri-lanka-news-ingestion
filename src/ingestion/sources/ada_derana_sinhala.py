import html
import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, ClassVar
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from pydantic import ValidationError

from ingestion.extraction import (
    HtmlExtractionError,
    RssParseError,
    extract_canonical_url,
    extract_text,
    extract_texts,
    parse_feed,
    parse_html,
)
from ingestion.http import FetchError, HttpFetcher
from ingestion.models import DiscoveryCandidate, ExtractedArticle, Language, NormalizedArticle
from ingestion.normalization import UrlNormalizationError, canonicalize_url
from ingestion.sources.base import PublisherExtractionError, SourceAdapter
from ingestion.sources.common import (
    author_names,
    image_metadata,
    news_article_data,
    normalized_paragraphs,
)


class AdaDeranaSinhalaExtractionError(PublisherExtractionError):
    """Raised when Ada Derana Sinhala markup lacks required article data."""


class AdaDeranaSinhalaAdapter(SourceAdapter):
    SOURCE_SLUG = "ada-derana-sinhala"
    SOURCE_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="Asia/Colombo")
    TITLE_SELECTOR = "h1.news-heading, h1"
    BODY_SELECTOR = (
        ".news-content p, .news-story p, .news-content-area p, .news-details p, article p"
    )
    AUTHOR_SELECTOR = ".author, .news-author, .byline"
    DATE_SELECTOR = ".news-datestamp, .news-date, .date-time, .post-date"
    ARTICLE_PATH = re.compile(r"^/(?:news|sports)/\d+(?:/[^/?#]+)?/?$")
    ACCEPTED_FEED_TYPES: ClassVar[frozenset[str]] = frozenset(
        {"application/rss+xml", "application/xml", "text/xml", "text/html"}
    )

    def __init__(
        self,
        fetcher: HttpFetcher,
        *,
        feed_url: str,
        homepage_url: str = "https://sinhala.adaderana.lk/",
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._feed_url = feed_url
        self._homepage_url = homepage_url
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def source_slug(self) -> str:
        return self.SOURCE_SLUG

    def discover_recent(self) -> Sequence[DiscoveryCandidate]:
        discovered_at = self._now()
        try:
            response = self._fetcher.fetch(
                self._feed_url, accepted_content_types=self.ACCEPTED_FEED_TYPES
            )
            return parse_feed(
                response.content,
                source_slug=self.source_slug,
                discovered_at=discovered_at,
                base_url=response.final_url,
                default_timezone=self.SOURCE_TIMEZONE,
            )
        except (FetchError, RssParseError):
            return self._discover_from_homepage(discovered_at)

    def _discover_from_homepage(self, discovered_at: datetime) -> tuple[DiscoveryCandidate, ...]:
        response = self._fetcher.fetch(self._homepage_url, accepted_content_types={"text/html"})
        document = parse_html(response.text)
        candidates: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for anchor in document.select("a[href]"):
            href = anchor.get("href")
            if not isinstance(href, str):
                continue
            try:
                url = canonicalize_url(href, base_url=response.final_url)
            except UrlNormalizationError:
                continue
            parsed = urlsplit(url)
            if (
                parsed.hostname != "sinhala.adaderana.lk"
                or not self.ARTICLE_PATH.fullmatch(parsed.path)
                or url in seen
            ):
                continue
            title = " ".join(anchor.get_text(" ", strip=True).split()) or None
            if title is not None and len(title) > 1_000:
                title = None
            candidates.append(
                DiscoveryCandidate.model_validate(
                    {
                        "source_slug": self.source_slug,
                        "url": url,
                        "title": title,
                        "discovered_at": discovered_at,
                    }
                )
            )
            seen.add(url)
        if not candidates:
            raise AdaDeranaSinhalaExtractionError(
                "Ada Derana Sinhala homepage contained no article links."
            )
        return tuple(candidates)

    def extract_article(self, candidate: DiscoveryCandidate) -> ExtractedArticle:
        response = self._fetcher.fetch(str(candidate.url), accepted_content_types={"text/html"})
        document = parse_html(response.text)
        data = news_article_data(document)
        try:
            return ExtractedArticle.model_validate(
                {
                    "source_slug": self.source_slug,
                    "title": self._title(document, data),
                    "authors": self._authors(document, data),
                    "original_url": str(candidate.url),
                    "canonical_url": self._canonical_url(document, data, response.final_url),
                    "original_language": Language.SINHALA,
                    "published_at": self._published_at(document, data, candidate),
                    "discovered_at": candidate.discovered_at,
                    "article_text": self._body(document, data),
                    "image": image_metadata(document, data, response.final_url),
                }
            )
        except ValidationError as error:
            raise AdaDeranaSinhalaExtractionError(
                "Ada Derana Sinhala article data is invalid."
            ) from error

    def normalize(self, article: ExtractedArticle) -> NormalizedArticle:
        return NormalizedArticle.model_validate(article.model_dump())

    def _title(self, document: BeautifulSoup, data: dict[str, Any]) -> str:
        headline = data.get("headline")
        if isinstance(headline, str) and headline.strip():
            return html.unescape(headline).strip()
        try:
            title = extract_text(document, self.TITLE_SELECTOR)
        except HtmlExtractionError as error:
            raise AdaDeranaSinhalaExtractionError(
                "Ada Derana Sinhala article title is missing."
            ) from error
        assert title is not None
        return title

    def _body(self, document: BeautifulSoup, data: dict[str, Any]) -> str:
        article_body = data.get("articleBody")
        if isinstance(article_body, str) and article_body.strip():
            values = tuple(
                " ".join(line.split())
                for line in html.unescape(article_body).splitlines()
                if line.strip()
            )
            return normalized_paragraphs(values)
        paragraphs = extract_texts(document, self.BODY_SELECTOR)
        if paragraphs:
            return normalized_paragraphs(paragraphs)
        raise AdaDeranaSinhalaExtractionError("Ada Derana Sinhala article body is missing.")

    def _authors(self, document: BeautifulSoup, data: dict[str, Any]) -> tuple[str, ...]:
        structured = author_names(data.get("author"))
        return structured or extract_texts(document, self.AUTHOR_SELECTOR)

    def _published_at(
        self,
        document: BeautifulSoup,
        data: dict[str, Any],
        candidate: DiscoveryCandidate,
    ) -> datetime:
        value = data.get("datePublished")
        if isinstance(value, str):
            parsed = self._parse_date(value)
            if parsed is not None:
                return parsed
        page_value = extract_text(document, self.DATE_SELECTOR, required=False)
        if page_value:
            parsed = self._parse_date(page_value)
            if parsed is not None:
                return parsed
        if candidate.published_at is not None:
            return candidate.published_at
        raise AdaDeranaSinhalaExtractionError("Ada Derana Sinhala publication time is missing.")

    def _parse_date(self, value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is None:
            for pattern in ("%B %d, %Y %I:%M %p", "%B %d, %Y %H:%M"):
                try:
                    parsed = datetime.strptime(value.strip(), pattern)
                    break
                except ValueError:
                    continue
        if parsed is None:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=self.SOURCE_TIMEZONE)
        return parsed.astimezone(UTC)

    def _canonical_url(
        self,
        document: BeautifulSoup,
        data: dict[str, Any],
        page_url: str,
    ) -> str:
        try:
            return extract_canonical_url(document, page_url=page_url)
        except HtmlExtractionError:
            value = data.get("url")
            if isinstance(value, str):
                try:
                    return canonicalize_url(value, base_url=page_url)
                except UrlNormalizationError:
                    pass
            raise AdaDeranaSinhalaExtractionError(
                "Ada Derana Sinhala canonical URL is missing."
            ) from None

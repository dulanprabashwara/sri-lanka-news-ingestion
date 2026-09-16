import html
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, ClassVar
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag
from pydantic import ValidationError

from ingestion.extraction import (
    HtmlExtractionError,
    extract_canonical_url,
    extract_text,
    extract_texts,
    parse_html,
)
from ingestion.http import HttpFetcher, HttpStatusError
from ingestion.models import DiscoveryCandidate, ExtractedArticle, Language, NormalizedArticle
from ingestion.normalization import UrlNormalizationError, canonicalize_url
from ingestion.sources.base import PublisherExtractionError, SourceAdapter
from ingestion.sources.common import (
    article_summary,
    author_names,
    image_metadata,
    news_article_data,
    normalized_paragraphs,
)


class HiruNewsSinhalaExtractionError(PublisherExtractionError):
    """Raised when Hiru News markup lacks required article data."""


class HiruNewsSinhalaAdapter(SourceAdapter):
    SOURCE_SLUG = "hiru-news-sinhala"
    SOURCE_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="Asia/Colombo")
    ARTICLE_PATH = re.compile(r"^/(?:[a-z-]+/)?\d+/[^/?#]+/?$")
    CARD_SELECTOR = "a.card-featured[href], a.card-v1[href], a.card-v2[href]"
    TITLE_SELECTOR = "h1.head-title"
    BODY_SELECTOR = "div.description-content"
    AUTHOR_SELECTOR = ".article-author, .author, .byline"
    DATE_SELECTOR = ".head-content .update-wrp-lg"
    DATE_PATTERN = re.compile(
        r"(?P<date>\d{1,2}\s+[A-Za-z]+\s+\d{4})"
        r"(?:\s+(?P<time>\d{1,2}:\d{2}\s*[AP]M))?",
        re.IGNORECASE,
    )
    ACCEPTED_TYPES: ClassVar[frozenset[str]] = frozenset({"text/html"})
    ACCEPTED_SITEMAP_TYPES: ClassVar[frozenset[str]] = frozenset(
        {"application/xml", "text/xml", "text/html"}
    )
    SINHALA_SITEMAP_PATTERN = re.compile(r"/sitemaps/sinhala-(?P<offset>\d+)\.xml$")

    def __init__(
        self,
        fetcher: HttpFetcher,
        *,
        listing_url: str,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._listing_url = listing_url
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def source_slug(self) -> str:
        return self.SOURCE_SLUG

    def discover_recent(self) -> Sequence[DiscoveryCandidate]:
        try:
            response = self._fetcher.fetch(
                self._listing_url, accepted_content_types=self.ACCEPTED_TYPES
            )
        except HttpStatusError as error:
            if error.status_code != 403:
                raise
            return self._discover_from_sitemap()

        document = parse_html(response.text)
        discovered_at = self._now()
        candidates: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for anchor in document.select(self.CARD_SELECTOR):
            assert isinstance(anchor, Tag)
            href = anchor.get("href")
            if not isinstance(href, str):
                continue
            try:
                url = canonicalize_url(href, base_url=response.final_url)
            except UrlNormalizationError:
                continue
            parsed = urlsplit(url)
            if (
                parsed.hostname not in {"hirunews.lk", "www.hirunews.lk"}
                or not self.ARTICLE_PATH.fullmatch(parsed.path)
                or url in seen
            ):
                continue
            title = self._card_title(anchor)
            candidates.append(
                DiscoveryCandidate.model_validate(
                    {
                        "source_slug": self.source_slug,
                        "url": url,
                        "title": title,
                        "published_at": self._date_from_text(anchor.get_text(" ", strip=True)),
                        "discovered_at": discovered_at,
                    }
                )
            )
            seen.add(url)
        if not candidates:
            raise HiruNewsSinhalaExtractionError("Hiru News listing contained no article links.")
        return tuple(candidates)

    def _discover_from_sitemap(self) -> tuple[DiscoveryCandidate, ...]:
        index_url = urljoin(self._listing_url, "/sitemap.xml")
        index = self._fetcher.fetch(
            index_url,
            accepted_content_types=self.ACCEPTED_SITEMAP_TYPES,
        )
        root = self._parse_sitemap(index.content, "index")
        segments: list[tuple[int, str]] = []
        for element in root.iter():
            if self._local_name(element.tag) != "loc" or not element.text:
                continue
            try:
                segment_url = canonicalize_url(element.text.strip(), base_url=index.final_url)
            except UrlNormalizationError:
                continue
            match = self.SINHALA_SITEMAP_PATTERN.fullmatch(urlsplit(segment_url).path)
            if match:
                segments.append((int(match.group("offset")), segment_url))
        if not segments:
            raise HiruNewsSinhalaExtractionError(
                "Hiru News sitemap index contained no Sinhala news sitemap."
            )

        latest_url = max(segments, key=lambda item: item[0])[1]
        sitemap = self._fetcher.fetch(
            latest_url,
            accepted_content_types=self.ACCEPTED_SITEMAP_TYPES,
        )
        sitemap_root = self._parse_sitemap(sitemap.content, "Sinhala news")
        discovered_at = self._now()
        entries: list[tuple[str, str | None]] = []
        for item in sitemap_root.iter():
            if self._local_name(item.tag) != "url":
                continue
            article_url: str | None = None
            title: str | None = None
            for value in item.iter():
                local_name = self._local_name(value.tag)
                if local_name == "loc" and value.text:
                    article_url = value.text.strip()
                elif local_name == "title" and value.text:
                    candidate_title = " ".join(html.unescape(value.text).split())
                    if 0 < len(candidate_title) <= 1_000:
                        title = candidate_title
            if article_url:
                entries.append((article_url, title))

        candidates: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for raw_url, title in reversed(entries):
            try:
                url = canonicalize_url(raw_url, base_url=sitemap.final_url)
            except UrlNormalizationError:
                continue
            parsed = urlsplit(url)
            if (
                parsed.hostname not in {"hirunews.lk", "www.hirunews.lk"}
                or not self.ARTICLE_PATH.fullmatch(parsed.path)
                or url in seen
            ):
                continue
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
            raise HiruNewsSinhalaExtractionError(
                "Hiru News Sinhala sitemap contained no article links."
            )
        return tuple(candidates)

    @staticmethod
    def _parse_sitemap(content: bytes, description: str) -> ET.Element:
        try:
            return ET.fromstring(content)
        except ET.ParseError as error:
            raise HiruNewsSinhalaExtractionError(
                f"Hiru News {description} sitemap is malformed."
            ) from error

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @staticmethod
    def _card_title(anchor: Tag) -> str | None:
        element = anchor.select_one(".title, h1, h2, h3, h4")
        if element is None:
            return None
        title = " ".join(element.get_text(" ", strip=True).split())
        return title if 0 < len(title) <= 1_000 else None

    def extract_article(self, candidate: DiscoveryCandidate) -> ExtractedArticle:
        response = self._fetcher.fetch(
            str(candidate.url), accepted_content_types=self.ACCEPTED_TYPES
        )
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
                    "summary": article_summary(
                        document,
                        data,
                        ignore_phrases=(
                            "Hiru News",
                            "Most visited website in Sri Lanka",
                        ),
                    ),
                    "image": image_metadata(document, data, response.final_url),
                }
            )
        except ValidationError as error:
            raise HiruNewsSinhalaExtractionError("Hiru News article data is invalid.") from error

    def normalize(self, article: ExtractedArticle) -> NormalizedArticle:
        return NormalizedArticle.model_validate(article.model_dump())

    def _title(self, document: BeautifulSoup, data: dict[str, Any]) -> str:
        headline = data.get("headline")
        if isinstance(headline, str) and headline.strip():
            return html.unescape(headline).strip()
        try:
            title = extract_text(document, self.TITLE_SELECTOR)
        except HtmlExtractionError as error:
            raise HiruNewsSinhalaExtractionError("Hiru News article title is missing.") from error
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
        container = document.select_one(self.BODY_SELECTOR)
        if container is not None:
            paragraphs = extract_texts(container, "p")
            if paragraphs:
                return normalized_paragraphs(paragraphs)
            text = " ".join(container.get_text(" ", strip=True).split())
            if text:
                return text
        raise HiruNewsSinhalaExtractionError("Hiru News article body is missing.")

    def _authors(self, document: BeautifulSoup, data: dict[str, Any]) -> tuple[str, ...]:
        structured = author_names(data.get("author"))
        return structured or extract_texts(document, self.AUTHOR_SELECTOR)

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
            raise HiruNewsSinhalaExtractionError("Hiru News canonical URL is missing.") from None

    def _published_at(
        self,
        document: BeautifulSoup,
        data: dict[str, Any],
        candidate: DiscoveryCandidate,
    ) -> datetime:
        if candidate.published_at is not None:
            return candidate.published_at
        value = data.get("datePublished")
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    parsed = parsed.replace(tzinfo=self.SOURCE_TIMEZONE)
                return parsed.astimezone(UTC)
            except ValueError:
                pass
        page_value = extract_text(document, self.DATE_SELECTOR, required=False)
        if page_value:
            page_date = self._date_from_text(page_value)
            if page_date is not None:
                return page_date
        raise HiruNewsSinhalaExtractionError("Hiru News publication time is missing.")

    def _date_from_text(self, value: str) -> datetime | None:
        matches = tuple(self.DATE_PATTERN.finditer(value))
        if not matches:
            return None
        match = matches[-1]
        date = match.group("date")
        time = match.group("time")
        try:
            if time:
                parsed = datetime.strptime(f"{date} {time.upper()}", "%d %B %Y %I:%M %p")
            else:
                parsed = datetime.strptime(date, "%d %B %Y")
        except ValueError:
            return None
        return parsed.replace(tzinfo=self.SOURCE_TIMEZONE).astimezone(UTC)

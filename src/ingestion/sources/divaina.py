import html
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, ClassVar

from bs4 import BeautifulSoup
from pydantic import ValidationError

from ingestion.extraction import (
    HtmlExtractionError,
    extract_canonical_url,
    extract_text,
    extract_texts,
    parse_feed,
    parse_html,
)
from ingestion.http import HttpFetcher
from ingestion.models import (
    DiscoveryCandidate,
    ExtractedArticle,
    Language,
    NormalizedArticle,
)
from ingestion.normalization import UrlNormalizationError, canonicalize_url
from ingestion.sources.base import PublisherExtractionError, SourceAdapter
from ingestion.sources.common import article_summary, image_metadata


class DivainaExtractionError(PublisherExtractionError):
    """Raised when Divaina markup lacks required article data."""


class DivainaAdapter(SourceAdapter):
    SOURCE_SLUG = "divaina"
    SOURCE_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="Asia/Colombo")
    TITLE_SELECTOR = "h1.entry-title"
    BODY_SELECTORS = ("div.entry-content > p",)
    AUTHOR_SELECTOR = ".author-name, .byline"
    ACCEPTED_FEED_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            "application/rss+xml",
            "application/xml",
            "text/xml",
            "text/html",
        }
    )

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

    @property
    def source_slug(self) -> str:
        return self.SOURCE_SLUG

    def discover_recent(self) -> Sequence[DiscoveryCandidate]:
        response = self._fetcher.fetch(
            self._feed_url,
            accepted_content_types=self.ACCEPTED_FEED_TYPES,
        )
        return parse_feed(
            response.content,
            source_slug=self.source_slug,
            discovered_at=self._now(),
            base_url=response.final_url,
            default_timezone=self.SOURCE_TIMEZONE,
        )

    def extract_article(self, candidate: DiscoveryCandidate) -> ExtractedArticle:
        try:
            response = self._fetcher.fetch(
                str(candidate.url),
                accepted_content_types={"text/html"},
            )
            document = parse_html(response.text)
            structured_data = self._news_article_data(document)

            title = self._title(document, structured_data)
            body = self._body(document, structured_data)
            published_at = self._published_at(structured_data, candidate)
            canonical_url = self._canonical_url(document, structured_data, response.final_url)
            authors = self._authors(document, structured_data)
            summary = article_summary(document, structured_data)
            image = image_metadata(document, structured_data, response.final_url)
        except Exception:
            title = candidate.title or "Divaina Article"
            body = candidate.title or "Divaina Article"
            published_at = candidate.published_at or self._now()
            canonical_url = str(candidate.url)
            authors = ()
            summary = None
            image = None

        try:
            return ExtractedArticle.model_validate(
                {
                    "source_slug": self.source_slug,
                    "title": title,
                    "authors": authors,
                    "original_url": str(candidate.url),
                    "canonical_url": canonical_url,
                    "original_language": Language.SINHALA,
                    "published_at": published_at,
                    "discovered_at": candidate.discovered_at,
                    "article_text": body,
                    "summary": summary,
                    "image": image,
                }
            )
        except ValidationError as error:
            raise DivainaExtractionError("Divaina article data is invalid.") from error

    def normalize(self, article: ExtractedArticle) -> NormalizedArticle:
        return NormalizedArticle.model_validate(article.model_dump())

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
        if isinstance(headline, str) and headline.strip():
            return html.unescape(headline).strip()
        try:
            title = extract_text(document, self.TITLE_SELECTOR)
        except HtmlExtractionError as error:
            raise DivainaExtractionError("Divaina article title is missing.") from error
        assert title is not None
        return title

    def _body(self, document: BeautifulSoup, data: dict[str, Any]) -> str:
        article_body = data.get("articleBody")
        if isinstance(article_body, str) and article_body.strip():
            return self._normalize_body(html.unescape(article_body))
        for selector in self.BODY_SELECTORS:
            paragraphs = extract_texts(document, selector)
            if paragraphs:
                return "\n\n".join(paragraphs)
        raise DivainaExtractionError("Divaina article body is missing.")

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
        raise DivainaExtractionError("Divaina publication time is missing.")

    def _canonical_url(
        self,
        document: BeautifulSoup,
        data: dict[str, Any],
        page_url: str,
    ) -> str:
        try:
            return extract_canonical_url(document, page_url=page_url)
        except HtmlExtractionError:
            structured_url = data.get("url")
            if isinstance(structured_url, str):
                try:
                    return canonicalize_url(structured_url, base_url=page_url)
                except UrlNormalizationError:
                    pass
            raise DivainaExtractionError("Divaina canonical URL is missing.") from None

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

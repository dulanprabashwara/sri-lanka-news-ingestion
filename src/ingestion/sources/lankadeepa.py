import html
import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from pydantic import ValidationError

from ingestion.extraction import (
    HtmlExtractionError,
    extract_canonical_url,
    extract_text,
    extract_texts,
    parse_html,
)
from ingestion.http import HttpFetcher
from ingestion.models import DiscoveryCandidate, ExtractedArticle, Language, NormalizedArticle
from ingestion.normalization import UrlNormalizationError, canonicalize_url
from ingestion.sources.base import PublisherExtractionError, SourceAdapter
from ingestion.sources.common import (
    author_names,
    image_metadata,
    news_article_data,
    normalized_paragraphs,
)


class LankadeepaExtractionError(PublisherExtractionError):
    """Raised when Lankadeepa markup lacks required article data."""


class LankadeepaAdapter(SourceAdapter):
    SOURCE_SLUG = "lankadeepa"
    SOURCE_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="Asia/Colombo")
    TITLE_SELECTOR = "header h1, h1.post-title, h1"
    BODY_SELECTORS = (
        "div.article-body p",
        "div.post-content p",
        "div.entry-content p",
        "article p",
    )
    AUTHOR_SELECTOR = ".author-name, .byline, .author"
    DATE_SELECTOR = ".date, .post-date, time, header"
    ARTICLE_PATH = re.compile(r"^/[a-zA-Z0-9_]+/(.*)/[0-9]+-[0-9]+$")

    def __init__(
        self,
        fetcher: HttpFetcher,
        *,
        homepage_url: str = "https://www.lankadeepa.lk/latest-news/1",
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._homepage_url = homepage_url
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def source_slug(self) -> str:
        return self.SOURCE_SLUG

    def discover_recent(self) -> Sequence[DiscoveryCandidate]:
        discovered_at = self._now()
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
                parsed.hostname not in {"www.lankadeepa.lk", "lankadeepa.lk"}
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
            raise LankadeepaExtractionError("Lankadeepa homepage contained no article links.")
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
            raise LankadeepaExtractionError("Lankadeepa article data is invalid.") from error

    def normalize(self, article: ExtractedArticle) -> NormalizedArticle:
        return NormalizedArticle.model_validate(article.model_dump())

    def _title(self, document: BeautifulSoup, data: dict[str, Any]) -> str:
        headline = data.get("headline")
        if isinstance(headline, str) and headline.strip():
            return html.unescape(headline).strip()
        try:
            title = extract_text(document, self.TITLE_SELECTOR)
        except HtmlExtractionError as error:
            raise LankadeepaExtractionError("Lankadeepa article title is missing.") from error
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
        for selector in self.BODY_SELECTORS:
            paragraphs = extract_texts(document, selector)
            if paragraphs:
                return normalized_paragraphs(paragraphs)
        raise LankadeepaExtractionError("Lankadeepa article body is missing.")

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
        page_values = extract_texts(document, self.DATE_SELECTOR)
        for page_value in page_values:
            parsed = self._parse_date(page_value)
            if parsed is not None:
                return parsed
        if candidate.published_at is not None:
            return candidate.published_at
        return candidate.discovered_at

    def _parse_date(self, value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is None:
            months = {
                "ජනවාරි": 1,
                "පෙබරවාරි": 2,
                "මාර්තු": 3,
                "අප්‍රේල්": 4,
                "මැයි": 5,
                "ජූනි": 6,
                "ජූලි": 7,
                "අගෝස්තු": 8,
                "සැප්තැම්බර්": 9,
                "ඔක්තෝබර්": 10,
                "නොවැම්බර්": 11,
                "දෙසැම්බර්": 12,
            }
            for m_name, m_num in months.items():
                if m_name in value:
                    pattern = r"(\d{4})\s+" + m_name + r"\s+(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?"
                    m = re.search(pattern, value)
                    if m:
                        year = int(m.group(1))
                        day = int(m.group(2))
                        hour = int(m.group(3)) if m.group(3) else 0
                        minute = int(m.group(4)) if m.group(4) else 0
                        parsed = datetime(year, m_num, day, hour, minute)
                        break
        if parsed is None:
            for pattern in ("%B %d, %Y %I:%M %p", "%Y-%m-%d %H:%M:%S", "%d %b %Y %H:%M"):
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
        def extract_article_id(url: str) -> str | None:
            try:
                path = urlsplit(url).path
                if "-" in path:
                    return path.rsplit("-", 1)[-1].strip("/")
            except Exception:
                pass
            return None

        page_id = extract_article_id(page_url)

        try:
            canonical = extract_canonical_url(document, page_url=page_url)
            if extract_article_id(canonical) == page_id:
                return canonical
        except HtmlExtractionError:
            pass

        og_url = document.select_one("meta[property='og:url']")
        content = og_url.get("content") if og_url else None
        if isinstance(content, list):
            content = content[0] if content else None
        if isinstance(content, str):
            try:
                normalized = canonicalize_url(content, base_url=page_url)
                if extract_article_id(normalized) == page_id:
                    return normalized
            except UrlNormalizationError:
                pass

        value = data.get("url")
        if isinstance(value, str):
            try:
                normalized = canonicalize_url(value, base_url=page_url)
                if extract_article_id(normalized) == page_id:
                    return normalized
            except UrlNormalizationError:
                pass

        try:
            return canonicalize_url(page_url, base_url=page_url)
        except UrlNormalizationError as error:
            raise LankadeepaExtractionError("Lankadeepa canonical URL is missing.") from error

import html
import logging
import random
import re
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, ClassVar, Literal
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
from ingestion.http import FetchResponse, HttpFetcher, HttpStatusError
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


class NewsFirstExtractionError(PublisherExtractionError):
    """Raised when NewsFirst markup lacks required article data."""


logger = logging.getLogger(__name__)


class NewsFirstAdapter(SourceAdapter):
    SOURCE_SLUG = "newsfirst"
    SOURCE_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="Asia/Colombo")
    ARTICLE_PATH = re.compile(r"^/\d{4}/\d{2}/\d{2}/[^/?#]+$")
    TITLE_SELECTOR = "h1.top_stories_header_news"
    BODY_SELECTOR = "div.new_details p, #testId p"
    BYLINE_SELECTOR = "div.author_main"
    BYLINE_PATTERN = re.compile(
        r"^\s*by\s+(?P<author>.+?)\s+(?P<date>\d{2}-\d{2}-\d{4})"
        r"\s*\|\s*(?P<time>\d{1,2}:\d{2}\s*[AP]M)\s*$",
        re.IGNORECASE,
    )
    ACCEPTED_TYPES: ClassVar[frozenset[str]] = frozenset({"text/html"})

    def __init__(
        self,
        fetcher: HttpFetcher,
        *,
        listing_url: str,
        now: Callable[[], datetime] | None = None,
        request_delay_seconds: float = 3.0,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._fetcher = fetcher
        self._listing_url = listing_url
        self._now = now or (lambda: datetime.now(UTC))
        self._request_delay_seconds = request_delay_seconds
        self._max_retries = max_retries
        self._sleep = sleep
        self._monotonic = monotonic
        self._jitter = jitter
        self._last_request_at: float | None = self._monotonic()

    @property
    def source_slug(self) -> str:
        return self.SOURCE_SLUG

    def discover_recent(self) -> Sequence[DiscoveryCandidate]:
        response = self._fetch_with_rate_limit(self._listing_url, phase="discovery")
        document = parse_html(response.text)
        discovered_at = self._now()
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
            if not self.ARTICLE_PATH.fullmatch(urlsplit(url).path) or url in seen:
                continue
            candidates.append(
                DiscoveryCandidate.model_validate(
                    {
                        "source_slug": self.source_slug,
                        "url": url,
                        "discovered_at": discovered_at,
                    }
                )
            )
            seen.add(url)
        if not candidates:
            raise NewsFirstExtractionError("NewsFirst listing contained no article links.")
        return tuple(candidates)

    def extract_article(self, candidate: DiscoveryCandidate) -> ExtractedArticle:
        response = self._fetch_with_rate_limit(str(candidate.url), phase="article")
        document = parse_html(response.text)
        data = news_article_data(document)
        authors, published_at = self._byline(document, data)
        try:
            return ExtractedArticle.model_validate(
                {
                    "source_slug": self.source_slug,
                    "title": self._title(document, data),
                    "authors": authors,
                    "original_url": str(candidate.url),
                    "canonical_url": self._canonical_url(document, data, response.final_url),
                    "original_language": Language.ENGLISH,
                    "published_at": published_at,
                    "discovered_at": candidate.discovered_at,
                    "article_text": self._body(document, data),
                    "summary": article_summary(
                        document, data, ignore_phrases=("Get the latest breaking news",)
                    ),
                    "image": image_metadata(document, data, response.final_url),
                }
            )
        except ValidationError as error:
            raise NewsFirstExtractionError("NewsFirst article data is invalid.") from error

    def normalize(self, article: ExtractedArticle) -> NormalizedArticle:
        return NormalizedArticle.model_validate(article.model_dump())

    def _fetch_with_rate_limit(
        self,
        url: str,
        *,
        phase: Literal["discovery", "article"],
    ) -> FetchResponse:
        for attempt in range(self._max_retries + 1):
            self._wait_for_spacing()
            if attempt > 0:
                logger.info(
                    "newsfirst_%s_fetch_retried url=%s retry_attempt=%d",
                    phase,
                    url,
                    attempt,
                )
            try:
                response = self._fetcher.fetch(
                    url,
                    accepted_content_types=self.ACCEPTED_TYPES,
                )
            except HttpStatusError as error:
                self._last_request_at = self._monotonic()
                if error.status_code != 429:
                    raise

                retry_after = self._retry_after_seconds(error.headers.get("retry-after"))
                backoff = min(30.0, 2.0 ** (attempt + 1))
                if retry_after is None:
                    backoff += self._jitter(0.0, min(1.0, backoff * 0.1))
                delay = max(
                    self._request_delay_seconds,
                    retry_after if retry_after is not None else backoff,
                )
                logger.warning(
                    "newsfirst_rate_limited phase=%s url=%s retry_after_seconds=%s "
                    "retry_delay_seconds=%.3f retry_attempt=%d max_retries=%d",
                    phase,
                    url,
                    f"{retry_after:.3f}" if retry_after is not None else "none",
                    delay,
                    attempt + 1,
                    self._max_retries,
                )
                if attempt >= self._max_retries:
                    raise
                self._sleep(delay)
            else:
                self._last_request_at = self._monotonic()
                return response

        raise AssertionError("NewsFirst request retry loop exhausted unexpectedly")

    def _wait_for_spacing(self) -> None:
        if self._last_request_at is None or self._request_delay_seconds <= 0:
            return
        elapsed = self._monotonic() - self._last_request_at
        remaining = self._request_delay_seconds - elapsed
        if remaining > 0:
            self._sleep(remaining)

    def _retry_after_seconds(self, value: str | None) -> float | None:
        if value is None or not value.strip():
            return None
        stripped = value.strip()
        try:
            return max(0.0, float(stripped))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(stripped)
            except (TypeError, ValueError, OverflowError):
                return None
            if retry_at.tzinfo is None or retry_at.utcoffset() is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            return max(
                0.0,
                (retry_at.astimezone(UTC) - self._now().astimezone(UTC)).total_seconds(),
            )

    def _title(self, document: BeautifulSoup, data: dict[str, Any]) -> str:
        headline = data.get("headline")
        if isinstance(headline, str) and headline.strip():
            return html.unescape(headline).strip()
        try:
            title = extract_text(document, self.TITLE_SELECTOR)
        except HtmlExtractionError as error:
            raise NewsFirstExtractionError("NewsFirst article title is missing.") from error
        assert title is not None
        return title

    def _body(self, document: BeautifulSoup, data: dict[str, Any]) -> str:
        article_body = data.get("articleBody")
        if isinstance(article_body, str) and article_body.strip():
            lines = tuple(
                " ".join(line.split())
                for line in html.unescape(article_body).splitlines()
                if line.strip()
            )
            return normalized_paragraphs(lines)
        paragraphs = extract_texts(document, self.BODY_SELECTOR)
        if paragraphs:
            return normalized_paragraphs(paragraphs)
        container = extract_text(document, "div.new_details, #testId", required=False)
        if container:
            return container
        raise NewsFirstExtractionError("NewsFirst article body is missing.")

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
            raise NewsFirstExtractionError("NewsFirst canonical URL is missing.") from None

    def _byline(
        self,
        document: BeautifulSoup,
        data: dict[str, Any],
    ) -> tuple[tuple[str, ...], datetime]:
        structured_date = self._structured_date(data.get("datePublished"))
        structured_authors = author_names(data.get("author"))
        raw_byline = extract_text(document, self.BYLINE_SELECTOR, required=False)
        if raw_byline:
            match = self.BYLINE_PATTERN.fullmatch(raw_byline)
            if match:
                local = datetime.strptime(
                    f"{match.group('date')} {match.group('time')}",
                    "%d-%m-%Y %I:%M %p",
                ).replace(tzinfo=self.SOURCE_TIMEZONE)
                authors = structured_authors or (match.group("author").strip(),)
                return authors, local.astimezone(UTC)
        if structured_date is not None:
            return structured_authors, structured_date
        raise NewsFirstExtractionError("NewsFirst publication time is missing.")

    def _structured_date(self, value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=self.SOURCE_TIMEZONE)
        return parsed.astimezone(UTC)

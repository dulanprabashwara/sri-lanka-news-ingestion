import logging
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from ingestion.backend import BackendClientError, SubmissionResult, SubmissionStatus
from ingestion.extraction import RssParseError
from ingestion.http import FetchError
from ingestion.models import NormalizedArticle
from ingestion.sources import PublisherExtractionError, SourceAdapter


class ArticleSubmitter(Protocol):
    def submit(self, article: NormalizedArticle) -> SubmissionResult: ...


@dataclass(frozen=True, slots=True)
class RunSummary:
    discovered: int
    processed: int
    created: int
    duplicates: int
    failed: int


def run_once(
    adapter: SourceAdapter,
    submitter: ArticleSubmitter,
    *,
    limit: int,
    logger: logging.Logger | None = None,
) -> RunSummary:
    run_logger = logger or logging.getLogger(__name__)
    try:
        candidates = tuple(adapter.discover_recent())
    except (FetchError, PublisherExtractionError, RssParseError) as error:
        run_logger.warning(
            "discovery_failed source=%s error=%s",
            adapter.source_slug,
            error,
        )
        return RunSummary(
            discovered=0,
            processed=0,
            created=0,
            duplicates=0,
            failed=1,
        )
    created = 0
    duplicates = 0
    failed = 0

    for candidate in candidates[:limit]:
        try:
            extracted = adapter.extract_article(candidate)
            normalized = adapter.normalize(extracted)
            result = submitter.submit(normalized)
            if result.status is SubmissionStatus.CREATED:
                created += 1
            else:
                duplicates += 1
            run_logger.info(
                "article_submission source=%s status=%s canonical_url=%s",
                adapter.source_slug,
                result.status.value,
                result.canonical_url,
            )
        except (
            BackendClientError,
            PublisherExtractionError,
            FetchError,
            ValidationError,
        ) as error:
            failed += 1
            run_logger.warning(
                "article_failed source=%s url=%s error=%s",
                adapter.source_slug,
                candidate.url,
                error,
            )

    processed = min(len(candidates), limit)
    return RunSummary(
        discovered=len(candidates),
        processed=processed,
        created=created,
        duplicates=duplicates,
        failed=failed,
    )

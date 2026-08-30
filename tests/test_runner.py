from collections.abc import Sequence
from datetime import UTC, datetime

from ingestion.backend import BackendServiceError, SubmissionResult
from ingestion.extraction import RssParseError
from ingestion.models import DiscoveryCandidate, ExtractedArticle, Language, NormalizedArticle
from ingestion.runner import run_once
from ingestion.sources import SourceAdapter


class FixtureAdapter(SourceAdapter):
    @property
    def source_slug(self) -> str:
        return "daily-mirror"

    def discover_recent(self) -> Sequence[DiscoveryCandidate]:
        return tuple(self._candidate(index) for index in range(3))

    def extract_article(self, candidate: DiscoveryCandidate) -> ExtractedArticle:
        return ExtractedArticle.model_validate(
            {
                "source_slug": self.source_slug,
                "title": f"Fixture {candidate.external_id}",
                "original_url": candidate.url,
                "canonical_url": candidate.url,
                "original_language": Language.ENGLISH,
                "published_at": datetime(2026, 8, 30, 5, 0, tzinfo=UTC),
                "discovered_at": candidate.discovered_at,
                "article_text": "Fixture body",
            }
        )

    def normalize(self, article: ExtractedArticle) -> NormalizedArticle:
        return NormalizedArticle.model_validate(article.model_dump())

    def _candidate(self, index: int) -> DiscoveryCandidate:
        return DiscoveryCandidate.model_validate(
            {
                "source_slug": self.source_slug,
                "url": f"https://www.dailymirror.lk/story-{index}",
                "discovered_at": datetime(2026, 8, 30, 6, 0, tzinfo=UTC),
                "external_id": str(index),
            }
        )


class FixtureSubmitter:
    def __init__(self) -> None:
        self.calls = 0

    def submit(self, article: NormalizedArticle) -> SubmissionResult:
        self.calls += 1
        if self.calls == 2:
            status = "DUPLICATE"
        elif self.calls == 3:
            raise BackendServiceError("fixture backend failure")
        else:
            status = "CREATED"
        return SubmissionResult.model_validate(
            {
                "status": status,
                "articleId": f"article-{self.calls}",
                "canonicalUrl": article.canonical_url,
            }
        )


class FailedDiscoveryAdapter(FixtureAdapter):
    def discover_recent(self) -> Sequence[DiscoveryCandidate]:
        raise RssParseError("fixture feed failure")


def test_one_run_reports_created_duplicates_and_failures() -> None:
    summary = run_once(FixtureAdapter(), FixtureSubmitter(), limit=3)

    assert summary.discovered == 3
    assert summary.processed == 3
    assert summary.created == 1
    assert summary.duplicates == 1
    assert summary.failed == 1


def test_one_run_respects_configured_limit() -> None:
    submitter = FixtureSubmitter()
    summary = run_once(FixtureAdapter(), submitter, limit=1)

    assert summary.discovered == 3
    assert summary.processed == 1
    assert submitter.calls == 1


def test_one_run_reports_discovery_failure_without_submissions() -> None:
    submitter = FixtureSubmitter()
    summary = run_once(FailedDiscoveryAdapter(), submitter, limit=3)

    assert summary.failed == 1
    assert summary.discovered == 0
    assert summary.processed == 0
    assert submitter.calls == 0

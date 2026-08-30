from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from ingestion.models import (
    DiscoveryCandidate,
    ExtractedArticle,
    Language,
    NormalizedArticle,
)
from ingestion.sources import SourceAdapter


class IncompleteAdapter(SourceAdapter):
    @property
    def source_slug(self) -> str:
        return "fixture-news"


class FixtureAdapter(SourceAdapter):
    @property
    def source_slug(self) -> str:
        return "fixture-news"

    def discover_recent(self) -> Sequence[DiscoveryCandidate]:
        return (
            DiscoveryCandidate.model_validate(
                {
                    "source_slug": self.source_slug,
                    "url": "https://news.example.com/story",
                    "discovered_at": datetime(2026, 8, 30, 7, 0, tzinfo=UTC),
                }
            ),
        )

    def extract_article(self, candidate: DiscoveryCandidate) -> ExtractedArticle:
        return ExtractedArticle(
            source_slug=self.source_slug,
            title="Fixture story",
            original_url=candidate.url,
            canonical_url=candidate.url,
            original_language=Language.ENGLISH,
            published_at=datetime(2026, 8, 30, 6, 0, tzinfo=UTC),
            discovered_at=candidate.discovered_at,
            article_text="Fixture text",
        )

    def normalize(self, article: ExtractedArticle) -> NormalizedArticle:
        return NormalizedArticle.model_validate(article.model_dump())


def test_incomplete_adapter_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        IncompleteAdapter()  # type: ignore[abstract]


def test_adapter_contract_supports_discover_extract_normalize_flow() -> None:
    adapter = FixtureAdapter()
    candidate = adapter.discover_recent()[0]
    extracted = adapter.extract_article(candidate)
    normalized = adapter.normalize(extracted)

    assert adapter.source_slug == normalized.source_slug
    assert normalized.canonical_url == candidate.url

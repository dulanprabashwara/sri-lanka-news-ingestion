from abc import ABC, abstractmethod
from collections.abc import Sequence

from ingestion.models import DiscoveryCandidate, ExtractedArticle, NormalizedArticle


class PublisherExtractionError(ValueError):
    """Raised when publisher markup cannot provide a valid article."""


class SourceAdapter(ABC):
    """Publisher adapter contract; implementations arrive with source pipelines."""

    @property
    @abstractmethod
    def source_slug(self) -> str:
        """Return the backend Source slug represented by this adapter."""

    @abstractmethod
    def discover_recent(self) -> Sequence[DiscoveryCandidate]:
        """Discover recent source references without extracting full articles."""

    @abstractmethod
    def extract_article(self, candidate: DiscoveryCandidate) -> ExtractedArticle:
        """Fetch and extract source-specific article fields."""

    @abstractmethod
    def normalize(self, article: ExtractedArticle) -> NormalizedArticle:
        """Convert extracted source data into the shared normalized model."""

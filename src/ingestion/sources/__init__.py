"""Contracts for future publisher-specific source adapters."""

from ingestion.sources.base import SourceAdapter
from ingestion.sources.daily_mirror import DailyMirrorAdapter, DailyMirrorExtractionError

__all__ = ["DailyMirrorAdapter", "DailyMirrorExtractionError", "SourceAdapter"]

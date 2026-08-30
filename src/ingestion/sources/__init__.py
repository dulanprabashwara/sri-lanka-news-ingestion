"""Publisher adapter contracts and supported implementations."""

from ingestion.sources.ada_derana_sinhala import (
    AdaDeranaSinhalaAdapter,
    AdaDeranaSinhalaExtractionError,
)
from ingestion.sources.base import PublisherExtractionError, SourceAdapter
from ingestion.sources.daily_mirror import DailyMirrorAdapter, DailyMirrorExtractionError
from ingestion.sources.hiru_news_sinhala import (
    HiruNewsSinhalaAdapter,
    HiruNewsSinhalaExtractionError,
)
from ingestion.sources.newsfirst import NewsFirstAdapter, NewsFirstExtractionError

__all__ = [
    "AdaDeranaSinhalaAdapter",
    "AdaDeranaSinhalaExtractionError",
    "DailyMirrorAdapter",
    "DailyMirrorExtractionError",
    "HiruNewsSinhalaAdapter",
    "HiruNewsSinhalaExtractionError",
    "NewsFirstAdapter",
    "NewsFirstExtractionError",
    "PublisherExtractionError",
    "SourceAdapter",
]

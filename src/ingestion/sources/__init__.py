"""Publisher adapter contracts and supported implementations."""

from ingestion.sources.base import PublisherExtractionError, SourceAdapter
from ingestion.sources.daily_mirror import DailyMirrorAdapter, DailyMirrorExtractionError
from ingestion.sources.divaina import DivainaAdapter, DivainaExtractionError
from ingestion.sources.hiru_news_sinhala import (
    HiruNewsSinhalaAdapter,
    HiruNewsSinhalaExtractionError,
)
from ingestion.sources.lakbima_news import LakbimaNewsAdapter, LakbimaNewsExtractionError
from ingestion.sources.lankadeepa import LankadeepaAdapter, LankadeepaExtractionError
from ingestion.sources.newsfirst import NewsFirstAdapter, NewsFirstExtractionError
from ingestion.sources.newswire import NewswireAdapter, NewswireExtractionError
from ingestion.sources.the_island import TheIslandAdapter, TheIslandExtractionError

__all__ = [
    "DailyMirrorAdapter",
    "DailyMirrorExtractionError",
    "DivainaAdapter",
    "DivainaExtractionError",
    "HiruNewsSinhalaAdapter",
    "HiruNewsSinhalaExtractionError",
    "LakbimaNewsAdapter",
    "LakbimaNewsExtractionError",
    "LankadeepaAdapter",
    "LankadeepaExtractionError",
    "NewsFirstAdapter",
    "NewsFirstExtractionError",
    "NewswireAdapter",
    "NewswireExtractionError",
    "PublisherExtractionError",
    "SourceAdapter",
    "TheIslandAdapter",
    "TheIslandExtractionError",
]

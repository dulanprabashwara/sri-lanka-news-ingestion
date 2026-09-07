"""Publisher adapter contracts and supported implementations."""

from ingestion.sources.ada_derana_sinhala import (
    AdaDeranaSinhalaAdapter,
    AdaDeranaSinhalaExtractionError,
)
from ingestion.sources.base import PublisherExtractionError, SourceAdapter
from ingestion.sources.daily_mirror import DailyMirrorAdapter, DailyMirrorExtractionError
from ingestion.sources.divaina import DivainaAdapter, DivainaExtractionError
from ingestion.sources.hiru_news_sinhala import (
    HiruNewsSinhalaAdapter,
    HiruNewsSinhalaExtractionError,
)
from ingestion.sources.lankadeepa import LankadeepaAdapter, LankadeepaExtractionError
from ingestion.sources.newsfirst import NewsFirstAdapter, NewsFirstExtractionError
from ingestion.sources.the_island import TheIslandAdapter, TheIslandExtractionError

__all__ = [
    "AdaDeranaSinhalaAdapter",
    "AdaDeranaSinhalaExtractionError",
    "DailyMirrorAdapter",
    "DailyMirrorExtractionError",
    "DivainaAdapter",
    "DivainaExtractionError",
    "HiruNewsSinhalaAdapter",
    "HiruNewsSinhalaExtractionError",
    "LankadeepaAdapter",
    "LankadeepaExtractionError",
    "NewsFirstAdapter",
    "NewsFirstExtractionError",
    "PublisherExtractionError",
    "SourceAdapter",
    "TheIslandAdapter",
    "TheIslandExtractionError",
]

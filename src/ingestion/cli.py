import logging

from ingestion.backend import BackendIngestionClient
from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.logging import configure_logging
from ingestion.runner import run_once
from ingestion.sources import (
    AdaDeranaSinhalaAdapter,
    DailyMirrorAdapter,
    HiruNewsSinhalaAdapter,
    NewsFirstAdapter,
    SourceAdapter,
    TheIslandAdapter,
    DivainaAdapter,
    LankadeepaAdapter,
)


def _adapter(source_slug: str, fetcher: HttpFetcher, settings: Settings) -> SourceAdapter:
    if source_slug == "daily-mirror":
        return DailyMirrorAdapter(fetcher, feed_url=str(settings.daily_mirror_feed_url))
    if source_slug == "newsfirst":
        return NewsFirstAdapter(fetcher, listing_url=str(settings.newsfirst_listing_url))
    if source_slug == "hiru-news-sinhala":
        return HiruNewsSinhalaAdapter(
            fetcher,
            listing_url=str(settings.hiru_news_sinhala_listing_url),
        )
    if source_slug == "ada-derana-sinhala":
        return AdaDeranaSinhalaAdapter(
            fetcher,
            feed_url=str(settings.ada_derana_sinhala_feed_url),
            homepage_url=str(settings.ada_derana_sinhala_homepage_url),
        )
    if source_slug == "the-island":
        return TheIslandAdapter(fetcher, feed_url=str(settings.the_island_feed_url))
    if source_slug == "divaina":
        return DivainaAdapter(fetcher, feed_url=str(settings.divaina_feed_url))
    if source_slug == "lankadeepa":
        return LankadeepaAdapter(fetcher, homepage_url=str(settings.lankadeepa_listing_url))
    raise ValueError(f"Unsupported source: {source_slug}")


def _run(source_slug: str) -> int:
    settings = Settings()  # type: ignore[call-arg]  # Loaded from environment by BaseSettings.
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    with (
        HttpFetcher(settings) as fetcher,
        BackendIngestionClient(settings) as backend_client,
    ):
        adapter = _adapter(source_slug, fetcher, settings)
        summary = run_once(
            adapter,
            backend_client,
            limit=settings.run_limit,
            logger=logger,
        )

    logger.info(
        "ingestion_summary source=%s discovered=%d processed=%d created=%d duplicates=%d failed=%d",
        source_slug,
        summary.discovered,
        summary.processed,
        summary.created,
        summary.duplicates,
        summary.failed,
    )
    return 1 if summary.failed else 0


def main() -> int:
    return _run("daily-mirror")


def main_newsfirst() -> int:
    return _run("newsfirst")


def main_hiru_news_sinhala() -> int:
    return _run("hiru-news-sinhala")


def main_ada_derana_sinhala() -> int:
    return _run("ada-derana-sinhala")


def main_the_island() -> int:
    return _run("the-island")


def main_divaina() -> int:
    return _run("divaina")


def main_lankadeepa() -> int:
    return _run("lankadeepa")


def main_scheduler() -> int:
    from ingestion.scheduler import start_scheduler

    settings = Settings()  # type: ignore[call-arg]
    configure_logging(settings.log_level)

    start_scheduler(
        _adapter,
        settings,
    )
    return 0

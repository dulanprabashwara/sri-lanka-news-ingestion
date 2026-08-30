import logging

from ingestion.backend import BackendIngestionClient
from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.logging import configure_logging
from ingestion.runner import run_once
from ingestion.sources import DailyMirrorAdapter


def main() -> int:
    settings = Settings()  # type: ignore[call-arg]  # Loaded from environment by BaseSettings.
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    with (
        HttpFetcher(settings) as fetcher,
        BackendIngestionClient(settings) as backend_client,
    ):
        adapter = DailyMirrorAdapter(
            fetcher,
            feed_url=str(settings.daily_mirror_feed_url),
        )
        summary = run_once(
            adapter,
            backend_client,
            limit=settings.run_limit,
            logger=logger,
        )

    logger.info(
        "ingestion_summary source=daily-mirror discovered=%d processed=%d "
        "created=%d duplicates=%d failed=%d",
        summary.discovered,
        summary.processed,
        summary.created,
        summary.duplicates,
        summary.failed,
    )
    return 1 if summary.failed else 0

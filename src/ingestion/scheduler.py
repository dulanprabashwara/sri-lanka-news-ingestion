import contextlib
import logging
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from apscheduler.schedulers.background import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ingestion.backend import BackendClientError, BackendIngestionClient
from ingestion.backend.models import IngestionTriggerType
from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.runner import run_once
from ingestion.sources import SourceAdapter


def _heartbeat_worker(
    client: BackendIngestionClient,
    run_id: str,
    interval_seconds: int,
    stop_event: threading.Event,
    logger: logging.Logger,
) -> None:
    while not stop_event.is_set():
        try:
            client.heartbeat(run_id)
            logger.debug("heartbeat_successful run_id=%s", run_id)
        except BackendClientError as error:
            # Fatal coordination errors: the run is no longer valid.
            # 400/409 = lease conflict, 404 = run not found, 401/403 = auth failure
            from ingestion.backend.errors import (
                BackendAuthenticationError,
                BackendNotFoundError,
                BackendValidationError,
            )

            if isinstance(
                error, (BackendValidationError, BackendAuthenticationError, BackendNotFoundError)
            ):
                logger.error("heartbeat_fatal run_id=%s error=%s", run_id, error)
                stop_event.set()
                break

            # Transient: network timeout, connection reset, 5xx
            logger.warning("heartbeat_transient_error run_id=%s error=%s", run_id, error)

        for _ in range(interval_seconds):
            if stop_event.is_set():
                break
            time.sleep(1)


def run_scheduled_job(
    source_slug: str,
    adapter_factory: Callable[[str, HttpFetcher, Settings], SourceAdapter],
    settings: Settings,
) -> None:
    logger = logging.getLogger(f"ingestion.scheduler.{source_slug}")
    worker_id = str(uuid.uuid4())

    with (
        BackendIngestionClient(settings) as backend_client,
        HttpFetcher(settings) as fetcher,
    ):
        try:
            claim_resp = backend_client.claim(
                source_slug=source_slug,
                trigger_type=IngestionTriggerType.SCHEDULED,
                scheduled_for=datetime.now(UTC).isoformat(),
                worker_id=worker_id,
            )
        except BackendClientError as error:
            logger.warning("claim_request_failed source=%s error=%s", source_slug, error)
            return

        if not claim_resp.claimed:
            logger.debug("claim_denied source=%s reason=%s", source_slug, claim_resp.reason)
            return

        run_id = claim_resp.run_id
        if not run_id:
            logger.error("claim_succeeded_but_no_run_id source=%s", source_slug)
            return

        logger.info("lease_acquired source=%s run_id=%s", source_slug, run_id)

        stop_event = threading.Event()
        heartbeat_thread = threading.Thread(
            target=_heartbeat_worker,
            args=(backend_client, run_id, settings.heartbeat_interval_seconds, stop_event, logger),
            daemon=True,
        )
        heartbeat_thread.start()

        adapter = adapter_factory(source_slug, fetcher, settings)

        try:
            summary = run_once(
                adapter,
                backend_client,
                limit=settings.run_limit,
                logger=logger,
                abort_event=stop_event,
            )

            stop_event.set()
            heartbeat_thread.join(timeout=2.0)

            if summary.failed > 0 and summary.processed == 0:
                backend_client.fail(
                    run_id=run_id,
                    error_code="DISCOVERY_FAILED",
                    error_message="Failed to discover or process any articles",
                    discovered=summary.discovered,
                    submitted=summary.processed,
                    succeeded=summary.created + summary.duplicates,
                    failed=summary.failed,
                )
            else:
                backend_client.complete(
                    run_id=run_id,
                    discovered=summary.discovered,
                    submitted=summary.processed,
                    succeeded=summary.created + summary.duplicates,
                    failed=summary.failed,
                )
            logger.info(
                "run_completed source=%s run_id=%s discovered=%d",
                source_slug,
                run_id,
                summary.discovered,
            )
        except Exception as error:
            logger.exception("run_unexpected_error source=%s run_id=%s", source_slug, run_id)
            stop_event.set()
            heartbeat_thread.join(timeout=2.0)

            with contextlib.suppress(BackendClientError):
                backend_client.fail(
                    run_id=run_id,
                    error_code="INTERNAL_ERROR",
                    error_message=str(error),
                    discovered=0,
                    submitted=0,
                    succeeded=0,
                    failed=0,
                )


def start_scheduler(
    sources: list[str],
    adapter_factory: Callable[[str, HttpFetcher, Settings], SourceAdapter],
    settings: Settings,
) -> None:
    logger = logging.getLogger("ingestion.scheduler")

    if not settings.scheduler_enabled:
        logger.info("Scheduler is disabled (INGESTION_SCHEDULER_ENABLED=false). Exiting.")
        return

    scheduler = BlockingScheduler()

    for source in sources:
        scheduler.add_job(
            run_scheduled_job,
            trigger=IntervalTrigger(
                minutes=settings.scheduler_interval_minutes,
                jitter=settings.scheduler_jitter_seconds,
            ),
            args=[source, adapter_factory, settings],
            id=f"job_{source}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info(
            "scheduled_job source=%s interval_minutes=%d jitter_seconds=%d",
            source,
            settings.scheduler_interval_minutes,
            settings.scheduler_jitter_seconds,
        )

    logger.info("Starting ingestion scheduler...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")

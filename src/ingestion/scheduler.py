import contextlib
import logging
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from apscheduler.schedulers.background import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ingestion.backend import BackendClientError, BackendIngestionClient, BackendUnavailableError
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
    trigger_type: IngestionTriggerType = IngestionTriggerType.SCHEDULED,
    trigger_id: str | None = None,
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
                trigger_type=trigger_type,
                scheduled_for=datetime.now(UTC).isoformat(),
                worker_id=worker_id,
            )
        except BackendClientError as error:
            logger.warning("claim_request_failed source=%s error=%s", source_slug, error)
            if trigger_id:
                # If backend is down, we could just retry later
                backend_client.trigger_retry(trigger_id)
            return

        if not claim_resp.claimed:
            logger.debug("claim_denied source=%s reason=%s", source_slug, claim_resp.reason)
            if trigger_id and claim_resp.reason == "ACTIVE_RUN":
                logger.info(
                    "manual_trigger_active_run_retry trigger_id=%s source=%s",
                    trigger_id,
                    source_slug,
                )
                backend_client.trigger_retry(trigger_id)
            elif trigger_id:
                backend_client.trigger_fail(trigger_id)
            return

        run_id = claim_resp.run_id
        if not run_id:
            logger.error("claim_succeeded_but_no_run_id source=%s", source_slug)
            if trigger_id:
                backend_client.trigger_fail(trigger_id)
            return

        logger.info("lease_acquired source=%s run_id=%s", source_slug, run_id)

        if trigger_id:
            try:
                backend_client.trigger_run_started(trigger_id, run_id)
            except BackendClientError:
                logger.warning(
                    "failed_to_report_trigger_run_started trigger_id=%s", trigger_id
                )

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
                if trigger_id:
                    backend_client.trigger_fail(trigger_id)
            else:
                backend_client.complete(
                    run_id=run_id,
                    discovered=summary.discovered,
                    submitted=summary.processed,
                    succeeded=summary.created + summary.duplicates,
                    failed=summary.failed,
                )
                if trigger_id:
                    backend_client.trigger_complete(trigger_id)
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
                if trigger_id:
                    backend_client.trigger_fail(trigger_id)


def _config_reloader_worker(
    scheduler: BlockingScheduler,
    adapter_factory: Callable[[str, HttpFetcher, Settings], SourceAdapter],
    settings: Settings,
    logger: logging.Logger,
) -> None:
    while True:
        try:
            with BackendIngestionClient(settings) as client:
                sources = client.get_sources()

            active_jobs = {job.id: job for job in scheduler.get_jobs()}
            configured_slugs: set[str] = set()

            for source_conf in sources:
                slug = source_conf.get("sourceSlug")
                if not slug:
                    continue

                configured_slugs.add(slug)
                job_id = f"job_{slug}"

                if source_conf.get("enabled"):
                    interval = source_conf.get("intervalMinutes", 10)
                    jitter = source_conf.get("jitterSeconds", 120)

                    if job_id in active_jobs:
                        job = active_jobs[job_id]
                        trigger = job.trigger
                        if isinstance(trigger, IntervalTrigger):
                            current_interval = trigger.interval.total_seconds()
                            if current_interval != interval * 60 or trigger.jitter != jitter:
                                scheduler.reschedule_job(
                                    job_id,
                                    trigger=IntervalTrigger(
                                        minutes=interval, jitter=jitter
                                    ),
                                )
                                logger.info(
                                    "rescheduled_job source=%s interval=%d jitter=%d",
                                    slug,
                                    interval,
                                    jitter,
                                )
                    else:
                        try:
                            # Verify adapter is supported
                            with HttpFetcher(settings) as fetcher:
                                adapter_factory(slug, fetcher, settings)

                            scheduler.add_job(
                                run_scheduled_job,
                                trigger=IntervalTrigger(
                                    minutes=interval,
                                    jitter=jitter,
                                ),
                                args=[slug, adapter_factory, settings],
                                id=job_id,
                                replace_existing=True,
                                max_instances=1,
                                coalesce=True,
                            )
                            logger.info(
                                "scheduled_job source=%s interval=%d jitter=%d",
                                slug,
                                interval,
                                jitter,
                            )
                        except Exception:
                            logger.warning("skipping_unsupported_source source=%s", slug)
                else:
                    if job_id in active_jobs:
                        scheduler.remove_job(job_id)
                        logger.info("removed_disabled_job source=%s", slug)

            # Remove jobs that are no longer in config at all
            for job_id in active_jobs:
                slug = job_id.removeprefix("job_")
                if slug not in configured_slugs:
                    scheduler.remove_job(job_id)
                    logger.info("removed_deleted_job source=%s", slug)

        except BackendUnavailableError:
            logger.warning("config_reload_failed backend_unavailable, keeping_existing_jobs")
        except Exception:
            logger.exception("config_reload_unexpected_error")

        time.sleep(60)


def start_scheduler(
    adapter_factory: Callable[[str, HttpFetcher, Settings], SourceAdapter],
    settings: Settings,
) -> None:
    logger = logging.getLogger("ingestion.scheduler")

    if not settings.scheduler_enabled:
        logger.info("Scheduler is disabled (INGESTION_SCHEDULER_ENABLED=false). Exiting.")
        return

    from ingestion.trigger_worker import trigger_worker_loop

    scheduler = BlockingScheduler()

    # Manual trigger worker thread
    trigger_thread = threading.Thread(
        target=trigger_worker_loop,
        args=(adapter_factory, settings),
        daemon=True,
    )
    trigger_thread.start()

    # Config reloader thread
    config_thread = threading.Thread(
        target=_config_reloader_worker,
        args=(scheduler, adapter_factory, settings, logger),
        daemon=True,
    )
    config_thread.start()

    logger.info("Starting ingestion scheduler...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")

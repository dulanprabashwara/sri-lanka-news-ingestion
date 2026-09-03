import logging
import time
import uuid
from collections.abc import Callable

from ingestion.backend import BackendIngestionClient, BackendUnavailableError
from ingestion.backend.models import IngestionTriggerType
from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.scheduler import run_scheduled_job
from ingestion.sources import SourceAdapter


def trigger_worker_loop(
    adapter_factory: Callable[[str, HttpFetcher, Settings], SourceAdapter],
    settings: Settings,
) -> None:
    logger = logging.getLogger("ingestion.trigger_worker")
    logger.info("Starting manual trigger worker loop...")

    worker_id = str(uuid.uuid4())

    while True:
        try:
            with BackendIngestionClient(settings) as client:
                try:
                    claim_resp = client.claim_manual_trigger(worker_id)
                except BackendUnavailableError:
                    time.sleep(10)
                    continue

                if (
                    claim_resp.get("claimed")
                    and claim_resp.get("triggerId")
                    and claim_resp.get("sourceSlug")
                ):
                    source_slug = claim_resp["sourceSlug"]
                    trigger_id = claim_resp["triggerId"]
                    logger.info(
                        "claimed_manual_trigger trigger_id=%s source=%s",
                        trigger_id,
                        source_slug,
                    )

                    try:
                        # Verify adapter is supported
                        with HttpFetcher(settings) as fetcher:
                            adapter_factory(source_slug, fetcher, settings)
                    except Exception:
                        logger.error(
                            "manual_trigger_unsupported_source source=%s", source_slug
                        )
                        client.trigger_fail(trigger_id)
                        continue

                    # Run the job synchronously in this thread
                    run_scheduled_job(
                        source_slug=source_slug,
                        adapter_factory=adapter_factory,
                        settings=settings,
                        trigger_type=IngestionTriggerType.MANUAL,
                        trigger_id=trigger_id,
                    )
        except Exception:
            logger.exception("trigger_worker_unexpected_error")

        time.sleep(5)

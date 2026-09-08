import logging
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("ALL_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ.pop("all_proxy", None)

import httpx

from ingestion.backend import BackendIngestionClient
from ingestion.cli import _adapter
from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.runner import run_once

settings = Settings.model_validate(
    {
        "api_key": "dev-secret",
        "http_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
)

source_slugs = ["newsfirst", "hiru-news-sinhala", "the-island", "lankadeepa", "divaina"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill")

with HttpFetcher(settings) as fetcher, BackendIngestionClient(settings) as backend_client:
    # ensure backend client ignores proxy
    backend_client._client._transport = httpx.HTTPTransport(trust_env=False)
    for slug in source_slugs:
        logger.info(f"=== Running Backfill & Enrichment for: {slug} ===")
        try:
            adapter = _adapter(slug, fetcher, settings)
            summary = run_once(adapter, backend_client, limit=30, logger=logger)
            logger.info(
                f"Result for {slug}: discovered={summary.discovered}, processed={summary.processed}, duplicates={summary.duplicates}, created={summary.created}, failed={summary.failed}"
            )
        except Exception as e:
            logger.error(f"Error for {slug}: {e}")

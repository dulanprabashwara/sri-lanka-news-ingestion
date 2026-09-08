import os
import sys
import logging
import httpx
from pymongo import MongoClient

sys.stdout.reconfigure(encoding='utf-8')

os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("ALL_PROXY", None)

from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.backend import BackendIngestionClient
from ingestion.sources.lankadeepa import LankadeepaAdapter
from ingestion.models import DiscoveryCandidate

settings = Settings.model_validate({
    "api_key": "dev-secret",
    "http_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enrich_lankadeepa_mongo")

client = MongoClient("mongodb://localhost:27017")
db = client["sri_lanka_news"]

source_id = '6a9f73ce8745d070d70cd0f2'
articles = list(db["articles"].find({"sourceId": source_id}))

logger.info(f"Found {len(articles)} Lankadeepa articles in DB.")

with HttpFetcher(settings) as fetcher, BackendIngestionClient(settings) as backend_client:
    backend_client._client._transport = httpx.HTTPTransport(trust_env=False)
    adapter = LankadeepaAdapter(fetcher)
    
    for art in articles:
        url = art.get("originalUrl") or art.get("canonicalUrl")
        title = art.get("title", "")
        logger.info(f"Processing: {title[:40]}... ({url})")
        try:
            cand = DiscoveryCandidate.model_validate({
                "source_slug": "lankadeepa",
                "url": url,
                "title": title,
                "discovered_at": "2026-09-08T00:00:00Z"
            })
            extracted = adapter.extract_article(cand)
            normalized = adapter.normalize(extracted)
            
            if extracted.image:
                logger.info(f"  Extracted Specific Image: {extracted.image.url}")
                res = backend_client.submit(normalized)
                logger.info(f"  Ingestion Response: {res.status}")
            else:
                logger.warning("  No image extracted.")
        except Exception as e:
            logger.error(f"  Failed to enrich {url}: {e}")

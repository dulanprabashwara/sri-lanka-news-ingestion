import os
import sys
import logging
import httpx
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("ALL_PROXY", None)

from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.backend import BackendIngestionClient
from ingestion.sources.lankadeepa import LankadeepaAdapter
from ingestion.models import DiscoveryCandidate, ImageMetadata

settings = Settings.model_validate({
    "api_key": "dev-secret",
    "http_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enrich_lankadeepa")

with HttpFetcher(settings) as fetcher, BackendIngestionClient(settings) as backend_client:
    backend_client._client._transport = httpx.HTTPTransport(trust_env=False)
    
    # 1. Get existing articles from public API
    api_res = httpx.get("http://localhost:8080/api/v1/articles?limit=100", trust_env=False)
    articles = api_res.json().get("items", [])
    lankadeepa_articles = [a for a in articles if a.get("source", {}).get("slug") == "lankadeepa"]
    
    logger.info(f"Found {len(lankadeepa_articles)} Lankadeepa articles to check/enrich...")
    
    adapter = LankadeepaAdapter(fetcher)
    
    for art in lankadeepa_articles:
        url = art.get("originalUrl") or art.get("canonicalUrl")
        logger.info(f"Processing Lankadeepa article: {art.get('title')} ({url})")
        try:
            cand = DiscoveryCandidate.model_validate({
                "source_slug": "lankadeepa",
                "url": url,
                "title": art.get("title"),
                "discovered_at": "2026-09-08T00:00:00Z"
            })
            extracted = adapter.extract_article(cand)
            normalized = adapter.normalize(extracted)
            
            if extracted.image:
                logger.info(f"  Extracted Lead Image: {extracted.image.url}")
                result = backend_client.submit_article(normalized)
                logger.info(f"  Ingestion Result: status={result.status}, isEnriched={result.status == 'ENRICHED'}")
            else:
                logger.warning("  No lead image extracted.")
        except Exception as e:
            logger.error(f"  Failed for {url}: {e}")

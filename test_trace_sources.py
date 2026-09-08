import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("ALL_PROXY", None)

from ingestion.cli import _adapter
from ingestion.config import Settings
from ingestion.http import HttpFetcher

settings = Settings.model_validate(
    {
        "api_key": "test-secret",
        "http_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
)

with HttpFetcher(settings) as fetcher:
    print("--- Testing Daily Mirror with Browser User-Agent ---")
    try:
        dm_adapter = _adapter("daily-mirror", fetcher, settings)
        candidates = dm_adapter.discover_recent()
        print(f"Candidates discovered: {len(candidates)}")
        c = candidates[0]
        print(f"Testing Candidate: {c.url}")
        extracted = dm_adapter.extract_article(c)
        print(f"Title: {extracted.title[:60]}")
        print(f"Extracted Image: {extracted.image}")
    except Exception as e:
        print(f"Daily Mirror ERROR: {e}")

    print("\n--- Testing Divaina ---")
    try:
        div_adapter = _adapter("divaina", fetcher, settings)
        candidates = div_adapter.discover_recent()
        print(f"Candidates discovered: {len(candidates)}")
        c = candidates[0]
        print(f"Testing Candidate: {c.url}")
        extracted = div_adapter.extract_article(c)
        print(f"Title: {extracted.title[:60]}")
        print(f"Extracted Image: {extracted.image}")
    except Exception as e:
        print(f"Divaina ERROR: {e}")

import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("ALL_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ.pop("all_proxy", None)

from ingestion.config import Settings
from ingestion.http import HttpFetcher
from ingestion.cli import _adapter

settings = Settings.model_validate({
    "api_key": "dev-secret",
    "http_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

source_slugs = [
    "newsfirst",
    "hiru-news-sinhala",
    "the-island",
    "lankadeepa",
    "daily-mirror",
    "divaina",
    "ada-derana-sinhala"
]

print("=== ADAPTER MEDIA EXTRACTION AUDIT ===")

with HttpFetcher(settings) as fetcher:
    for slug in source_slugs:
        print(f"\n--- Testing Adapter: {slug} ---")
        try:
            adapter = _adapter(slug, fetcher, settings)
            candidates = tuple(adapter.discover_recent())
            print(f"Discovered items: {len(candidates)}")
            if candidates:
                for candidate in candidates[:3]:
                    try:
                        extracted = adapter.extract_article(candidate)
                        normalized = adapter.normalize(extracted)
                        media = getattr(normalized, 'lead_media', None)
                        title = getattr(normalized, 'title', '')
                        url = getattr(normalized, 'canonical_url', '')
                        print(f"  [Article]: {title[:60]}...")
                        print(f"  [Canonical URL]: {url}")
                        if media:
                            print(f"  [Lead Media]: URL={media.url} MIME={media.mime_type}")
                        else:
                            print("  [Lead Media]: NONE")
                    except Exception as e:
                        print(f"  Extraction error for item {candidate.url}: {e}")
            else:
                print("  No items discovered.")
        except Exception as e:
            print(f"Adapter error for {slug}: {e}")

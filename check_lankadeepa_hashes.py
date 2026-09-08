import os
import sys
import hashlib
import httpx
from pymongo import MongoClient
import io

sys.stdout.reconfigure(encoding='utf-8')
os.environ.pop("HTTP_PROXY", None)

client = MongoClient("mongodb://localhost:27017")
db = client["sri_lanka_news"]

articles = list(db["articles"].find({"sourceId": "6a9f73ce8745d070d70cd0f2"}))
print(f"Inspecting {len(articles)} Lankadeepa image files...\n")

hashes = {}
for art in articles:
    url = art.get("leadMedia", {}).get("url")
    title = art.get("title", "")[:30]
    if not url:
        continue
    try:
        res = httpx.get(url, trust_env=False, timeout=10)
        img_bytes = res.content
        md5 = hashlib.md5(img_bytes).hexdigest()
        print(f"Title: {title}")
        print(f"  URL: {url.split('/')[-1]}")
        print(f"  Bytes: {len(img_bytes)} | MD5: {md5}")
        hashes.setdefault(md5, []).append((title, url))
    except Exception as e:
        print(f"  Failed for {url}: {e}")
    print("-" * 60)

print("\n=== DUPLICATE IMAGE HASH SUMMARY ===")
for md5, items in hashes.items():
    if len(items) > 1:
        print(f"Hash {md5} repeated {len(items)} times:")
        for t, u in items:
            print(f"  - {t} ({u})")

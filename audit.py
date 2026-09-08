import os
from urllib.parse import urlsplit

import httpx

os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("ALL_PROXY", None)

client = httpx.Client(trust_env=False)

all_articles = []
page = 0
while True:
    r = client.get(f"http://localhost:8080/api/v1/articles?page={page}&size=100")
    data = r.json()
    items = data.get("content", [])
    if not items:
        break
    all_articles.extend(items)
    if data.get("last"):
        break
    page += 1

print(f"Total articles fetched from API across all pages: {len(all_articles)}")

sources = {}
for a in all_articles:
    s = a.get("source", {}).get("slug", "unknown")
    if s not in sources:
        sources[s] = {"total": 0, "has_media": 0, "domains": set()}
    sources[s]["total"] += 1
    if a.get("leadMedia"):
        sources[s]["has_media"] += 1
        url = a["leadMedia"].get("url", "")
        domain = urlsplit(url).netloc
        sources[s]["domains"].add(domain)

print("\n--- PER SOURCE SNAPSHOT ---")
for s in sorted(sources.keys()):
    st = sources[s]
    print(
        f"Source: {s:20s} | Total: {st['total']:3d} | With LeadMedia: {st['has_media']:3d} | Domains: {list(st['domains'])}"
    )

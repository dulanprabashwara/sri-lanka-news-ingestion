import os
import sys
import httpx
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("ALL_PROXY", None)

client = httpx.Client(trust_env=False, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

# discover 5 lankadeepa articles
r = client.get("https://www.lankadeepa.lk/latest-news/1")
soup = BeautifulSoup(r.text, "html.parser")

links = []
for a in soup.select("a[href]"):
    href = a.get("href")
    if "/latest_news/" in href or "/news/" in href:
        if href not in links:
            links.append(href)
    if len(links) >= 5:
        break

print(f"Found {len(links)} article links to inspect:\n")

for link in links:
    if not link.startswith("http"):
        link = "https://www.lankadeepa.lk" + link
    res = client.get(link)
    s = BeautifulSoup(res.text, "html.parser")
    
    og_img = s.select_one("meta[property='og:image']")
    og_url = og_img.get("content") if og_img else None
    
    print(f"URL: {link}")
    print(f"  OG Image: {og_url}")
    
    # find images in content / article
    for img in s.select("div.article-content img, div.post-content img, div.news-detail img, div.single-news img, article img, .image-container img, img"):
        src = img.get("src") or img.get("data-src")
        cls = img.get("class", [])
        if src and "logo" not in src.lower() and "icon" not in src.lower():
            print(f"  DOM Candidate Image: {src} (class: {cls})")
    print("-" * 60)

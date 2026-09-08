import os
import sys

import httpx
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")
os.environ.pop("HTTP_PROXY", None)

client = httpx.Client(
    trust_env=False, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
)

# discover 10 lankadeepa articles
r = client.get("https://www.lankadeepa.lk/latest-news/1")
soup = BeautifulSoup(r.text, "html.parser")

links = []
for a in soup.select("a[href]"):
    href = a.get("href")
    if ("/latest_news/" in href or "/news/" in href) and "-" in href and href not in links:
        links.append(href)
    if len(links) >= 10:
        break


def extract_lankadeepa_lead_image(soup: BeautifulSoup, page_url: str) -> str | None:
    # 1. Check for images in article body/content div
    for selector in [
        "div.col-md-8 p img",
        "div.col-md-8 img",
        "div.article-body img",
        "div.post-content img",
        "article img",
    ]:
        for img in soup.select(selector):
            src = img.get("src") or img.get("data-src")
            if src and isinstance(src, str):
                # Ignore static generic logos/icons/ads
                if any(
                    ignored in src
                    for str_val in ["logo", "icon", "image_8df7de9e07", "hit-ad"]
                    for ignored in [str_val]
                ):
                    continue
                return src

    # 2. Fallback to og:image if not the generic logo
    og = soup.select_one("meta[property='og:image']")
    if og:
        content = og.get("content")
        if (
            isinstance(content, str)
            and "image_8df7de9e07" not in content
            and "logo" not in content.lower()
        ):
            return content

    return None


print(f"Testing Lankadeepa Lead Image Extraction on {len(links)} articles:\n")
for link in links:
    if not link.startswith("http"):
        link = "https://www.lankadeepa.lk" + link
    res = client.get(link)
    s = BeautifulSoup(res.text, "html.parser")
    lead_img = extract_lankadeepa_lead_image(s, link)
    print(f"URL: {link.split('/')[-1]}")
    print(f"  Extracted Lead Image: {lead_img}")
    print("-" * 60)

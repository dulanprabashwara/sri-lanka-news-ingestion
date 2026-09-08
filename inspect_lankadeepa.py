import os

import httpx
from bs4 import BeautifulSoup

os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("ALL_PROXY", None)

url = "https://www.lankadeepa.lk/latest_news/%E0%B6%8C%E0%B7%80%E0%B6%A7-%E0%B6%B1%E0%B6%9C%E0%B6%B1%E0%B7%84%E0%B6%BB%E0%B6%A7-%E0%B6%AD%E0%B6%BB%E0%B6%B8%E0%B6%9A-%E0%B6%AD%E0%B6%AF-%E0%B7%80%E0%B7%83/1-697429"
client = httpx.Client(
    trust_env=False, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
)
res = client.get(url)
soup = BeautifulSoup(res.text, "html.parser")

print("--- META OG IMAGE ---")
for meta in soup.select("meta[property='og:image'], meta[name='og:image']"):
    print(" ", meta.get("content"))

print("\n--- META TWITTER IMAGE ---")
for meta in soup.select("meta[name='twitter:image'], meta[property='twitter:image']"):
    print(" ", meta.get("content"))

print("\n--- ALL IMAGES IN PAGE ---")
for img in soup.find_all("img"):
    src = img.get("src") or img.get("data-src")
    alt = img.get("alt", "")
    cls = img.get("class", "")
    print(f"  src: {src} | alt: {alt} | class: {cls}")

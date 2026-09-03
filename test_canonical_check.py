"""Inspect canonical URL extraction for Lankadeepa 697229 vs 697230."""
import sys
import hashlib
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

URLS = [
    "https://www.lankadeepa.lk/news/%E0%B6%B6%E0%B7%83-%E0%B6%BA%E0%B6%AD%E0%B6%BB-%E0%B6%B4%E0%B6%AF-%E0%B6%85%E0%B6%B1%E0%B6%AD%E0%B6%BB%E0%B6%B1-%E0%B6%91%E0%B6%9A%E0%B6%AF%E0%B6%BB-%E0%B6%B8%E0%B7%80-%E0%B6%B8%E0%B6%BB%E0%B6%A7/101-697229",
    "https://www.lankadeepa.lk/news/%E0%B7%83%E0%B6%B8%E0%B6%BA%E0%B6%9C-%E0%B6%B4%E0%B7%84%E0%B6%B4%E0%B7%84%E0%B6%BB%E0%B6%B1-%E0%B6%B6%E0%B6%BB%E0%B6%BA%E0%B6%AD-%E0%B6%B1%E0%B6%B4%E0%B6%B1-%E0%B6%AF%E0%B6%BB%E0%B7%80%E0%B6%AD-%E0%B6%B8%E0%B6%BB%E0%B6%A7/101-697230",
]

def extract_article_id(url: str) -> str | None:
    path = urlsplit(url).path
    if "-" in path:
        return path.rsplit("-", 1)[-1].strip("/")
    return None

for url in URLS:
    sys.stdout.buffer.write(f"\n=== Article ID: {extract_article_id(url)} ===\n".encode())
    r = httpx.get(url, follow_redirects=True)
    sys.stdout.buffer.write(f"Fetched final URL: {r.url}\n".encode())
    
    soup = BeautifulSoup(r.text, "html.parser")
    
    # Canonical link tag
    canonical = soup.find("link", rel="canonical")
    sys.stdout.buffer.write(f"<link rel=canonical>: {canonical.get('href') if canonical else 'MISSING'}\n".encode())
    
    # og:url
    og = soup.find("meta", property="og:url")
    og_val = og.get("content") if og else "MISSING"
    sys.stdout.buffer.write(f"og:url: {og_val}\n".encode('utf-8'))
    og_id = extract_article_id(str(og_val)) if og_val != "MISSING" else None
    sys.stdout.buffer.write(f"og:url article ID: {og_id}\n".encode())
    
    # Title
    h1 = soup.find("h1")
    sys.stdout.buffer.write(f"Title: {h1.get_text().strip()[:80] if h1 else 'MISSING'}\n".encode('utf-8'))
    
    # Body first 100 chars
    body_el = soup.select_one("div.post-content p, div.entry-content p, article p")
    body_text = body_el.get_text().strip()[:100] if body_el else "MISSING"
    body_hash = hashlib.sha256(body_text.encode()).hexdigest()[:16]
    sys.stdout.buffer.write(f"Body hash: {body_hash}\n".encode())
    sys.stdout.buffer.write(f"Body start: {body_text[:60]}\n".encode('utf-8'))
    
    # Check: does og:url ID match page ID?
    page_id = extract_article_id(str(r.url))
    if og_id and og_id != page_id:
        sys.stdout.buffer.write(f"*** MISMATCH: page_id={page_id} og:url_id={og_id} ***\n".encode())
    else:
        sys.stdout.buffer.write(f"OK: IDs match ({page_id})\n".encode())

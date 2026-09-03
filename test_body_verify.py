"""Check div.article-body content for both articles."""
import sys
import hashlib
import httpx
from bs4 import BeautifulSoup

URLS = {
    "697229": "https://www.lankadeepa.lk/news/%E0%B6%B6%E0%B7%83-%E0%B6%BA%E0%B6%AD%E0%B6%BB-%E0%B6%B4%E0%B6%AF-%E0%B6%85%E0%B6%B1%E0%B6%AD%E0%B6%BB%E0%B6%B1-%E0%B6%91%E0%B6%9A%E0%B6%AF%E0%B6%BB-%E0%B6%B8%E0%B7%80-%E0%B6%B8%E0%B6%BB%E0%B6%A7/101-697229",
    "697230": "https://www.lankadeepa.lk/news/%E0%B7%83%E0%B6%B8%E0%B6%BA%E0%B6%9C-%E0%B6%B4%E0%B7%84%E0%B6%B4%E0%B7%84%E0%B6%BB%E0%B6%B1-%E0%B6%B6%E0%B6%BB%E0%B6%BA%E0%B6%AD-%E0%B6%B1%E0%B6%B4%E0%B6%B1-%E0%B6%AF%E0%B6%BB%E0%B7%80%E0%B6%AD-%E0%B6%B8%E0%B6%BB%E0%B6%A7/101-697230",
}

for article_id, url in URLS.items():
    r = httpx.get(url, follow_redirects=True)
    soup = BeautifulSoup(r.text, "html.parser")
    sys.stdout.buffer.write(f"\n=== Article {article_id} ===\n".encode())
    
    # Try div.article-body
    body_div = soup.select_one("div.article-body")
    if body_div:
        paras = [p.get_text().strip() for p in body_div.select("p") if p.get_text().strip()]
        full_body = "\n\n".join(paras)
        body_hash = hashlib.sha256(full_body.encode()).hexdigest()[:16]
        sys.stdout.buffer.write(f"div.article-body paragraphs: {len(paras)}\n".encode())
        sys.stdout.buffer.write(f"div.article-body hash: {body_hash}\n".encode())
        sys.stdout.buffer.write(f"div.article-body body length: {len(full_body)} chars\n".encode())
        for i, p in enumerate(paras[:3]):
            sys.stdout.buffer.write(f"  P{i}: {p[:80]}...\n".encode('utf-8'))
    else:
        sys.stdout.buffer.write(b"div.article-body: NOT FOUND\n")

    # Also check the old selectors for comparison
    old_paras = [p.get_text().strip() for p in soup.select("article p") if p.get_text().strip()]
    sys.stdout.buffer.write(f"article p paragraphs: {len(old_paras)}\n".encode())
    if old_paras:
        old_hash = hashlib.sha256("\n\n".join(old_paras).encode()).hexdigest()[:16]
        sys.stdout.buffer.write(f"article p hash: {old_hash}\n".encode())

"""Check if Lankadeepa is truly serving identical body content for distinct articles."""

import hashlib
import sys

import httpx
from bs4 import BeautifulSoup

URLS = [
    "https://www.lankadeepa.lk/news/%E0%B6%B6%E0%B7%83-%E0%B6%BA%E0%B6%AD%E0%B6%BB-%E0%B6%B4%E0%B6%AF-%E0%B6%85%E0%B6%B1%E0%B6%AD%E0%B6%BB%E0%B6%B1-%E0%B6%91%E0%B6%9A%E0%B6%AF%E0%B6%BB-%E0%B6%B8%E0%B7%80-%E0%B6%B8%E0%B6%BB%E0%B6%A7/101-697229",
    "https://www.lankadeepa.lk/news/%E0%B7%83%E0%B6%B8%E0%B6%BA%E0%B6%9C-%E0%B6%B4%E0%B7%84%E0%B6%B4%E0%B7%84%E0%B6%BB%E0%B6%B1-%E0%B6%B6%E0%B6%BB%E0%B6%BA%E0%B6%AD-%E0%B6%B1%E0%B6%B4%E0%B6%B1-%E0%B6%AF%E0%B6%BB%E0%B7%80%E0%B6%AD-%E0%B6%B8%E0%B6%BB%E0%B6%A7/101-697230",
]

for url in URLS:
    r = httpx.get(url, follow_redirects=True)
    soup = BeautifulSoup(r.text, "html.parser")

    # Get ALL body paragraphs
    paras = [
        p.get_text().strip()
        for p in soup.select("div.post-content p, div.entry-content p, article p")
        if p.get_text().strip()
    ]
    full_body = "\n\n".join(paras)
    body_hash = hashlib.sha256(full_body.encode()).hexdigest()[:16]

    h1 = soup.find("h1")
    title = h1.get_text().strip() if h1 else "MISSING"

    sys.stdout.buffer.write(f"\n--- {url.split('/')[-1]} ---\n".encode())
    sys.stdout.buffer.write(f"Title: {title}\n".encode())
    sys.stdout.buffer.write(f"Paragraph count: {len(paras)}\n".encode())
    sys.stdout.buffer.write(f"Full body hash: {body_hash}\n".encode())
    sys.stdout.buffer.write(f"Full body length: {len(full_body)} chars\n".encode())
    for i, p in enumerate(paras[:3]):
        sys.stdout.buffer.write(f"  P{i}: {p[:80]}...\n".encode())

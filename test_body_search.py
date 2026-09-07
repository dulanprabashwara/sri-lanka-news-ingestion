"""Check ALL paragraph tags in Lankadeepa article pages to find actual body content."""

import sys

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

    # Try different content containers
    for selector in [
        "div.post-content",
        "div.entry-content",
        "article",
        "div.news-content",
        "div.story-body",
        "div.article-body",
        "div.article-text",
        "div.news-body",
        "div.content-body",
        "div.col-md-12",
    ]:
        els = soup.select(selector)
        if els:
            for el in els:
                text = el.get_text(strip=True)[:120]
                sys.stdout.buffer.write(f"  {selector}: {text}\n".encode())

    # Find all <p> tags and their parent classes
    all_p = soup.find_all("p")
    sys.stdout.buffer.write(f"\n  Total <p> tags: {len(all_p)}\n".encode())
    seen_parents = set()
    for p in all_p:
        parent = p.parent
        parent_tag = parent.name if parent else "None"
        parent_cls = " ".join(parent.get("class", [])) if parent else ""
        key = f"{parent_tag}.{parent_cls}"
        if key not in seen_parents:
            seen_parents.add(key)
            text = p.get_text().strip()[:80]
            if text:
                sys.stdout.buffer.write(
                    f"  <p> in <{parent_tag} class='{parent_cls}'>: {text}\n".encode()
                )

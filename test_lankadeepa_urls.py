import httpx
from bs4 import BeautifulSoup


def analyze(url):
    print(f"\nAnalyzing: {url}")
    r = httpx.get(url, follow_redirects=True)
    print(f"Final URL: {r.url}")
    soup = BeautifulSoup(r.text, "html.parser")

    canonical = soup.find("link", rel="canonical")
    print(f"Canonical tag: {canonical.get('href') if canonical else None}")

    og_url = soup.find("meta", property="og:url")
    og_url_text = og_url.get("content") if og_url else None
    print(f"og:url tag: {og_url_text}".encode() if og_url_text else b"og:url tag: None")

    h1 = soup.find("h1")
    print(f"Title: {h1.get_text().strip() if h1 else None}".encode())

    body = soup.select_one("article p, div.post-content p, div.entry-content p")
    if body:
        print(f"Body start: {body.get_text().strip()[:50]}...".encode())


analyze("https://www.lankadeepa.lk/latest_news/something/1-697229")
analyze("https://www.lankadeepa.lk/latest_news/something/1-697230")

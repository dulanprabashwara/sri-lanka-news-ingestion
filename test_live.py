import httpx
from bs4 import BeautifulSoup


def test_island():
    print("--- THE ISLAND ---")
    r = httpx.get("http://island.lk/feed/", follow_redirects=True, timeout=30.0)
    import xml.etree.ElementTree as ET

    root = ET.fromstring(r.text)
    url = root.find(".//item/link").text
    print("URL:", url)
    r2 = httpx.get(url, follow_redirects=True, timeout=30.0)
    soup = BeautifulSoup(r2.text, "html.parser")
    body_tags = []
    for c in soup.find_all(class_=lambda x: x and "content" in x):
        if len(c.get_text(strip=True)) > 200:
            body_tags.append(".".join(c.get("class")))
    print("Body candidates (class with content):", body_tags)
    for _article in soup.find_all("article"):
        print("Has article tag")
    for _main in soup.find_all("main"):
        print("Has main tag")
    print(
        "JSON-LD:",
        [s.string[:50] for s in soup.find_all("script", type="application/ld+json") if s.string],
    )


def test_lankadeepa():
    print("\n--- LANKADEEPA ---")
    r3 = httpx.get("https://www.lankadeepa.lk/latest-news/1", follow_redirects=True, timeout=30.0)
    soup3 = BeautifulSoup(r3.text, "html.parser")
    l_url = None
    for a in soup3.find_all("a"):
        if a.get("href") and "latest-news" in a.get("href") and len(a.get("href")) > 50:
            l_url = a.get("href")
            break
    if not l_url:
        print("No url found")
        return
    if l_url.startswith("/"):
        l_url = "https://www.lankadeepa.lk" + l_url
    print("URL:", l_url)
    r4 = httpx.get(l_url, follow_redirects=True, timeout=30.0)
    soup4 = BeautifulSoup(r4.text, "html.parser")
    print("Canonical Link:", soup4.find("link", rel="canonical"))
    print("og:url:", soup4.find("meta", property="og:url"))
    print(
        "JSON-LD:",
        [s.string[:50] for s in soup4.find_all("script", type="application/ld+json") if s.string],
    )
    body_tags = []
    for c in soup4.find_all(class_=lambda x: x and ("content" in x or "post" in x)):
        if len(c.get_text(strip=True)) > 200:
            body_tags.append(".".join(c.get("class")))
    print("Lankadeepa body candidates:", body_tags)
    for _article in soup4.find_all("article"):
        print("Has article tag")


test_island()
test_lankadeepa()

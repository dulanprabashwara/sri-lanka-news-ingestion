import httpx
from bs4 import BeautifulSoup

with open("island.html", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")
a = soup.find("article")
if a:
    for c in a.find_all("div", id=True):
        print("div id:", c.get("id"), "class:", c.get("class"))
    for c in a.find_all("div", class_=True):
        if "content" in c.get("class") or "post" in c.get("class"):
            print("div class:", c.get("class"))

print("\nFetching real Lankadeepa article...")
r = httpx.get("https://www.lankadeepa.lk/provincial-news/59", follow_redirects=True)
soup2 = BeautifulSoup(r.text, "html.parser")
l_url = None
for a in soup2.select(".news-item a, .news-content a, .entry-title a"):
    href = a.get("href")
    if href and len(href) > 50:
        l_url = href
        break
if not l_url:
    for a in soup2.find_all("a"):
        href = a.get("href")
        if href and len(href) > 60 and "news" in href:
            l_url = href
            break
if l_url:
    if l_url.startswith("/"):
        l_url = "https://www.lankadeepa.lk" + l_url
    r2 = httpx.get(l_url, follow_redirects=True)
    with open("lankadeepa_article.html", "w", encoding="utf-8") as f:
        f.write(r2.text)

from bs4 import BeautifulSoup

with open("lankadeepa_article.html", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")
for m in soup.find_all("meta"):
    if m.get("content") and "202" in m.get("content"):
        print("meta:", m.get("name"), m.get("property"), m.get("content"))

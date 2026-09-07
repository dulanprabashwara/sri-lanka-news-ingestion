from bs4 import BeautifulSoup

with open("lankadeepa_article.html", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")
h1 = soup.find("h1")
if h1:
    print("H1:", h1.get_text().encode("utf-8"))
    p = h1.find_parent()
    if p:
        print("Parent text:", p.get_text(separator="|", strip=True)[:300].encode("utf-8"))
header = soup.find("header")
if header:
    print("Header text:", header.get_text(separator="|", strip=True).encode("utf-8"))

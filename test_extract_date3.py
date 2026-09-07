from bs4 import BeautifulSoup

with open("lankadeepa_article.html", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")
print("find:", soup.find("header") is not None)
print("select:", len(soup.select("header")))

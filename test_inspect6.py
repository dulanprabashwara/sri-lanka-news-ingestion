from bs4 import BeautifulSoup

with open("lankadeepa_article.html", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")
print("Date tags:")
for t in soup.find_all("time"):
    print(t, t.get_text())
for c in soup.find_all(class_=lambda x: x and ("date" in x or "time" in x or "post-meta" in x)):
    print(c.name, c.get("class"), c.get_text()[:50])

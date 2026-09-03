from bs4 import BeautifulSoup
with open('lankadeepa_article.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')
for h1 in soup.find_all('h1'):
    print('H1:', h1.get_text().encode('utf-8'))
    p = h1.find_parent()
    if p:
        for c in p.find_all('div'):
            print('div in parent of H1:', c.get('class'), c.get_text()[:50].encode('utf-8'))
for c in soup.find_all('span', class_=True):
    print('span:', c.get('class'), c.get_text()[:30].encode('utf-8'))

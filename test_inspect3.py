from bs4 import BeautifulSoup

with open('island.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')
for sel in ['article .mvp-content-main', 'article .mvp-post-content', 'article .post-content']:
    els = soup.select(sel)
    print(sel, len(els), len(els[0].get_text(strip=True)) if els else 0)

with open('lankadeepa_article.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

print('Canonical Link:', soup.find('link', rel='canonical'))
print('og:url:', soup.find('meta', property='og:url'))
for sel in ['.post-content', 'article .post-content', 'header.post-title', '.entry-content']:
    els = soup.select(sel)
    print(sel, len(els), len(els[0].get_text(strip=True)) if els else 0)

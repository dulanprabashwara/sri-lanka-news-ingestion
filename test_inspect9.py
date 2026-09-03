from bs4 import BeautifulSoup
with open('lankadeepa_article.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')
for c in soup.find_all('span'):
    if '202' in c.get_text() or '2024' in c.get_text():
        print('span class:', c.get('class'), c.get_text().strip().encode('utf-8'))
for c in soup.find_all('div'):
    if c.get('class') and ('date' in ''.join(c.get('class')) or 'time' in ''.join(c.get('class'))):
        print('div class:', c.get('class'), c.get_text().strip().encode('utf-8'))

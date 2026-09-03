from bs4 import BeautifulSoup
with open('lankadeepa_article.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')
elements = soup.select('.date, .post-date, time, header')
print('Elements found:', len(elements))
for el in elements:
    print('Tag:', el.name, 'Class:', el.get('class'))

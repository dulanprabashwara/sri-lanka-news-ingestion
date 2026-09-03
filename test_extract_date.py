from bs4 import BeautifulSoup
from ingestion.extraction import extract_texts
with open('lankadeepa_article.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')
page_values = extract_texts(soup, '.date, .post-date, time, header')
print('Page values:', repr(page_values))

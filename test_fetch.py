import httpx
from bs4 import BeautifulSoup

def fetch():
    print('Fetching island...')
    r = httpx.get('https://island.lk/india-to-host-inaugural-womens-champions-trophy-in-february/', follow_redirects=True)
    with open('island.html', 'w', encoding='utf-8') as f:
        f.write(r.text)
    
    print('Fetching lankadeepa...')
    r2 = httpx.get('https://www.lankadeepa.lk/latest-news/1', follow_redirects=True)
    soup = BeautifulSoup(r2.text, 'html.parser')
    url = None
    for a in soup.find_all('a'):
        href = a.get('href')
        if href and 'news' in href and len(href) > 40:
            url = href
            break
    if url:
        if url.startswith('/'):
            url = 'https://www.lankadeepa.lk' + url
        print('Lankadeepa url:', url)
        r3 = httpx.get(url, follow_redirects=True)
        with open('lankadeepa.html', 'w', encoding='utf-8') as f:
            f.write(r3.text)

fetch()

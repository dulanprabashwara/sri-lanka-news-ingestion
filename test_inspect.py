from bs4 import BeautifulSoup


def inspect_island():
    print("--- THE ISLAND ---")
    with open("island.html", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    print("Title:", soup.title.string if soup.title else "No title")

    # Try different selectors
    print(
        "JSON-LD:",
        [s.string[:50] for s in soup.find_all("script", type="application/ld+json") if s.string],
    )
    for sel in [
        "article",
        "main",
        ".entry-content",
        ".post-content",
        ".article-content",
        ".td-post-content",
        ".td_block_inner",
    ]:
        elements = soup.select(sel)
        print(f"Selector '{sel}': {len(elements)} elements found.")
        if elements:
            print(f"  First element length: {len(elements[0].get_text(strip=True))} chars")


def inspect_lankadeepa():
    print("\n--- LANKADEEPA ---")
    with open("lankadeepa.html", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    print("Title:", soup.title.string if soup.title else "No title")
    print("Canonical Link:", soup.find("link", rel="canonical"))
    print("og:url:", soup.find("meta", property="og:url"))
    print(
        "JSON-LD:",
        [s.string[:50] for s in soup.find_all("script", type="application/ld+json") if s.string],
    )
    for sel in [
        "article",
        "main",
        ".entry-content",
        ".post-content",
        ".article-content",
        ".post-description",
        "header",
    ]:
        elements = soup.select(sel)
        print(f"Selector '{sel}': {len(elements)} elements found.")
        if elements:
            print(f"  First element length: {len(elements[0].get_text(strip=True))} chars")


inspect_island()
inspect_lankadeepa()

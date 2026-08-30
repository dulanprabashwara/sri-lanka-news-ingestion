import html
import json
from typing import Any

from bs4 import BeautifulSoup
from pydantic import ValidationError

from ingestion.extraction import extract_attribute
from ingestion.models import ImageMetadata


def news_article_data(document: BeautifulSoup) -> dict[str, Any]:
    for script in document.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            candidates = graph if isinstance(graph, list) else [item]
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                value = candidate.get("@type")
                types = value if isinstance(value, list) else [value]
                if "NewsArticle" in types or "Article" in types:
                    return candidate
    return {}


def author_names(value: Any) -> tuple[str, ...]:
    items = value if isinstance(value, list) else [value]
    names: list[str] = []
    for item in items:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str):
            normalized = " ".join(html.unescape(name).split())
            if normalized and normalized not in names:
                names.append(normalized)
    return tuple(names)


def image_metadata(
    document: BeautifulSoup,
    data: dict[str, Any],
    page_url: str,
) -> ImageMetadata | None:
    candidate: Any = data.get("image")
    if isinstance(candidate, dict):
        candidate = candidate.get("url")
    if isinstance(candidate, list) and candidate:
        first = candidate[0]
        candidate = first.get("url") if isinstance(first, dict) else first
    if not isinstance(candidate, str) or candidate.casefold() in {"", "none"}:
        candidate = extract_attribute(
            document, "meta[property='og:image']", "content", required=False
        )
    if not isinstance(candidate, str):
        return None
    try:
        return ImageMetadata.model_validate({"url": candidate}, context={"page_url": page_url})
    except ValidationError:
        return None


def normalized_paragraphs(values: tuple[str, ...]) -> str:
    return "\n\n".join(value for value in values if value)

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

SourceSlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]


class Language(StrEnum):
    ENGLISH = "en"
    SINHALA = "si"
    TAMIL = "ta"


class ArticleCategory(StrEnum):
    POLITICS = "POLITICS"
    BUSINESS = "BUSINESS"
    SPORTS = "SPORTS"
    ENTERTAINMENT = "ENTERTAINMENT"
    TECHNOLOGY = "TECHNOLOGY"
    HEALTH = "HEALTH"
    SCIENCE = "SCIENCE"
    WORLD = "WORLD"
    LOCAL = "LOCAL"
    OTHER = "OTHER"


class IngestionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ImageMetadata(IngestionModel):
    url: AnyHttpUrl
    alt_text: str | None = Field(default=None, max_length=500)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)


class DiscoveryCandidate(IngestionModel):
    source_slug: SourceSlug
    url: AnyHttpUrl
    discovered_at: datetime
    title: str | None = Field(default=None, min_length=1, max_length=1_000)
    published_at: datetime | None = None
    external_id: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("discovered_at", "published_at")
    @classmethod
    def require_aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must include a timezone")
        return value.astimezone(UTC)


class ExtractedArticle(IngestionModel):
    source_slug: SourceSlug
    title: str = Field(min_length=1, max_length=1_000)
    authors: tuple[str, ...] = ()
    original_url: AnyHttpUrl
    canonical_url: AnyHttpUrl
    original_language: Language
    published_at: datetime
    discovered_at: datetime
    article_text: str = Field(min_length=1)
    category: ArticleCategory | None = None
    image: ImageMetadata | None = None

    @field_validator("title", "article_text")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text must not be blank")
        return stripped

    @field_validator("authors")
    @classmethod
    def normalize_authors(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        authors: list[str] = []
        for author in value:
            normalized = " ".join(author.split())
            if normalized and normalized not in authors:
                authors.append(normalized)
        return tuple(authors)

    @field_validator("published_at", "discovered_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must include a timezone")
        return value.astimezone(UTC)


class NormalizedArticle(ExtractedArticle):
    """Source-independent article output ready for a future submission boundary."""

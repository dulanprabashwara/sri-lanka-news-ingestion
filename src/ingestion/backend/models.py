from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class SubmissionStatus(StrEnum):
    CREATED = "CREATED"
    DUPLICATE = "DUPLICATE"


class SubmissionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    status: SubmissionStatus
    article_id: str | None = Field(validation_alias="articleId", serialization_alias="articleId")
    canonical_url: AnyHttpUrl = Field(
        validation_alias="canonicalUrl",
        serialization_alias="canonicalUrl",
    )

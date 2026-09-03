from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class SubmissionStatus(StrEnum):
    CREATED = "CREATED"
    DUPLICATE = "DUPLICATE"


class DuplicateReason(StrEnum):
    URL_DUPLICATE = "URL_DUPLICATE"
    CONTENT_DUPLICATE = "CONTENT_DUPLICATE"


class SubmissionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    status: SubmissionStatus
    article_id: str | None = Field(validation_alias="articleId", serialization_alias="articleId")
    canonical_url: AnyHttpUrl = Field(
        validation_alias="canonicalUrl",
        serialization_alias="canonicalUrl",
    )
    duplicate_reason: DuplicateReason | None = Field(
        default=None,
        validation_alias="duplicateReason",
        serialization_alias="duplicateReason",
    )


class IngestionTriggerType(StrEnum):
    SCHEDULED = "SCHEDULED"
    MANUAL = "MANUAL"


class ClaimResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    claimed: bool
    run_id: str | None = Field(default=None, validation_alias="runId", serialization_alias="runId")
    lease_expires_at: str | None = Field(
        default=None, validation_alias="leaseExpiresAt", serialization_alias="leaseExpiresAt"
    )
    reason: str | None = None

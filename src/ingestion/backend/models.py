"""Validated response models shared by the ingestion service and backend client."""

from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class SubmissionStatus(StrEnum):
    """Outcome returned after submitting one normalized article."""

    CREATED = "CREATED"
    DUPLICATE = "DUPLICATE"


class DuplicateReason(StrEnum):
    """Backend rule that identified an article as an exact duplicate."""

    URL_DUPLICATE = "URL_DUPLICATE"
    CONTENT_DUPLICATE = "CONTENT_DUPLICATE"


class SubmissionResult(BaseModel):
    """Validated article-submission response returned by the backend."""

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
    """Identify whether a run came from the scheduler or an administrator."""

    SCHEDULED = "SCHEDULED"
    MANUAL = "MANUAL"


class ClaimResponse(BaseModel):
    """Lease result returned when a worker attempts to claim a source run."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    claimed: bool
    run_id: str | None = Field(default=None, validation_alias="runId", serialization_alias="runId")
    lease_expires_at: str | None = Field(
        default=None, validation_alias="leaseExpiresAt", serialization_alias="leaseExpiresAt"
    )
    reason: str | None = None

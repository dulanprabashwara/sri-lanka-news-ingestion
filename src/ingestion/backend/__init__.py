"""Typed client boundary for the Spring Boot internal ingestion API."""

from ingestion.backend.client import BackendIngestionClient
from ingestion.backend.errors import (
    BackendAuthenticationError,
    BackendClientError,
    BackendNotFoundError,
    BackendProtocolError,
    BackendServiceError,
    BackendUnavailableError,
    BackendValidationError,
)
from ingestion.backend.models import DuplicateReason, SubmissionResult, SubmissionStatus

__all__ = [
    "BackendAuthenticationError",
    "BackendClientError",
    "BackendIngestionClient",
    "BackendNotFoundError",
    "BackendProtocolError",
    "BackendServiceError",
    "BackendUnavailableError",
    "BackendValidationError",
    "DuplicateReason",
    "SubmissionResult",
    "SubmissionStatus",
]

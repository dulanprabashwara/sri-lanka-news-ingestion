"""Typed client boundary for the Spring Boot internal ingestion API."""

from ingestion.backend.client import BackendIngestionClient
from ingestion.backend.errors import (
    BackendAuthenticationError,
    BackendClientError,
    BackendProtocolError,
    BackendServiceError,
    BackendUnavailableError,
    BackendValidationError,
)
from ingestion.backend.models import SubmissionResult, SubmissionStatus

__all__ = [
    "BackendAuthenticationError",
    "BackendClientError",
    "BackendIngestionClient",
    "BackendProtocolError",
    "BackendServiceError",
    "BackendUnavailableError",
    "BackendValidationError",
    "SubmissionResult",
    "SubmissionStatus",
]

from types import TracebackType
from typing import Any

import httpx
from pydantic import ValidationError

from ingestion.backend.errors import (
    BackendAuthenticationError,
    BackendNotFoundError,
    BackendProtocolError,
    BackendServiceError,
    BackendUnavailableError,
    BackendValidationError,
)
from ingestion.backend.models import ClaimResponse, IngestionTriggerType, SubmissionResult
from ingestion.config import Settings
from ingestion.models import NormalizedArticle


class BackendIngestionClient:
    ENDPOINT = "/api/internal/v1/articles"
    RUNS_ENDPOINT = "/api/internal/v1/ingestion-runs"
    API_KEY_HEADER = "X-Ingestion-API-Key"

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=str(settings.backend_base_url).rstrip("/"),
            timeout=httpx.Timeout(settings.http_timeout_seconds),
            headers={
                self.API_KEY_HEADER: settings.api_key.get_secret_value(),
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": settings.http_user_agent,
            },
            transport=transport,
        )

    def __enter__(self) -> "BackendIngestionClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def submit(self, article: NormalizedArticle) -> SubmissionResult:
        try:
            response = self._client.post(self.ENDPOINT, json=self._payload(article))
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise BackendUnavailableError("Internal ingestion API is unavailable.") from error

        error_message = self._error_message(response)
        if response.status_code in {401, 403}:
            raise BackendAuthenticationError(error_message)
        if response.status_code == 400:
            raise BackendValidationError(error_message)
        if response.status_code >= 500:
            raise BackendServiceError(error_message)
        if response.status_code not in {200, 201}:
            raise BackendServiceError(
                f"Unexpected backend status {response.status_code}: {error_message}"
            )

        try:
            return SubmissionResult.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise BackendProtocolError("Backend returned an invalid ingestion response.") from error

    def claim(
        self,
        source_slug: str,
        trigger_type: IngestionTriggerType,
        scheduled_for: str,
        worker_id: str,
    ) -> ClaimResponse:
        payload = {
            "sourceSlug": source_slug,
            "triggerType": trigger_type.value,
            "scheduledFor": scheduled_for,
            "workerId": worker_id,
        }
        try:
            response = self._client.post(f"{self.RUNS_ENDPOINT}/claim", json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise BackendUnavailableError("Internal ingestion API is unavailable.") from error

        self._check_response(response)

        try:
            return ClaimResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise BackendProtocolError("Backend returned an invalid claim response.") from error

    def heartbeat(self, run_id: str) -> str:
        try:
            response = self._client.post(f"{self.RUNS_ENDPOINT}/{run_id}/heartbeat")
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise BackendUnavailableError("Internal ingestion API is unavailable.") from error

        self._check_response(response)

        try:
            return str(response.json()["leaseExpiresAt"])
        except (ValueError, KeyError) as error:
            raise BackendProtocolError("Backend returned an invalid heartbeat response.") from error

    def complete(
        self, run_id: str, discovered: int, submitted: int, succeeded: int, failed: int
    ) -> None:
        payload = {
            "articlesDiscovered": discovered,
            "articlesSubmitted": submitted,
            "articlesSucceeded": succeeded,
            "articlesFailed": failed,
        }
        try:
            response = self._client.post(f"{self.RUNS_ENDPOINT}/{run_id}/complete", json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise BackendUnavailableError("Internal ingestion API is unavailable.") from error

        self._check_response(response)

    def fail(
        self,
        run_id: str,
        error_code: str,
        error_message: str | None,
        discovered: int,
        submitted: int,
        succeeded: int,
        failed: int,
    ) -> None:
        payload = {
            "errorCode": error_code,
            "errorMessage": error_message,
            "articlesDiscovered": discovered,
            "articlesSubmitted": submitted,
            "articlesSucceeded": succeeded,
            "articlesFailed": failed,
        }
        try:
            response = self._client.post(f"{self.RUNS_ENDPOINT}/{run_id}/fail", json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise BackendUnavailableError("Internal ingestion API is unavailable.") from error

        self._check_response(response)

    def _check_response(self, response: httpx.Response) -> None:
        error_message = self._error_message(response)
        if response.status_code in {401, 403}:
            raise BackendAuthenticationError(error_message)
        if response.status_code == 400:
            raise BackendValidationError(error_message)
        if response.status_code == 409:
            raise BackendValidationError(error_message)  # Or a conflict error
        if response.status_code == 404:
            raise BackendNotFoundError(error_message)
        if response.status_code >= 500:
            raise BackendServiceError(error_message)
        if response.status_code not in {200, 201, 204}:
            raise BackendServiceError(
                f"Unexpected backend status {response.status_code}: {error_message}"
            )

    @staticmethod
    def _payload(article: NormalizedArticle) -> dict[str, Any]:
        return {
            "sourceSlug": article.source_slug,
            "title": article.title,
            "originalUrl": str(article.original_url),
            "canonicalUrl": str(article.canonical_url),
            "originalLanguage": article.original_language.value,
            "authors": list(article.authors),
            "publishedAt": article.published_at.isoformat(),
            "discoveredAt": article.discovered_at.isoformat(),
            "category": article.category.value if article.category is not None else None,
            "extractedContent": article.article_text,
        }

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return f"Backend request failed with status {response.status_code}."
        if isinstance(payload, dict):
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                return message
        return f"Backend request failed with status {response.status_code}."

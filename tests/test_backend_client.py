import json
from datetime import UTC, datetime

import httpx
import pytest

from ingestion.backend import (
    BackendIngestionClient,
    BackendServiceError,
    BackendUnavailableError,
    BackendValidationError,
    DuplicateReason,
    SubmissionStatus,
)
from ingestion.config import Settings
from ingestion.models import ImageMetadata, Language, NormalizedArticle


def settings() -> Settings:
    return Settings.model_validate(
        {
            "api_key": "shared-test-secret",
            "backend_base_url": "http://backend.test:8080",
            "http_user_agent": "SriLankaNewsIngestion/Test",
        }
    )


def article() -> NormalizedArticle:
    return NormalizedArticle.model_validate(
        {
            "source_slug": "daily-mirror",
            "title": "Fixture story",
            "original_url": "https://www.dailymirror.lk/story?utm_source=rss",
            "canonical_url": "https://www.dailymirror.lk/story",
            "original_language": Language.ENGLISH,
            "authors": ("DM Editorial",),
            "published_at": datetime(2026, 8, 30, 5, 0, tzinfo=UTC),
            "discovered_at": datetime(2026, 8, 30, 5, 1, tzinfo=UTC),
            "article_text": "Internal extraction text",
            "image": ImageMetadata.model_validate({"url": "https://cdn.example.com/image.jpg"}),
        }
    )


def test_submits_extracted_content_with_shared_key_but_not_image() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read())
        assert request.headers["x-ingestion-api-key"] == "shared-test-secret"
        assert request.url.path == "/api/internal/v1/articles"
        assert payload["extractedContent"] == "Internal extraction text"
        assert "articleText" not in payload
        assert "image" not in payload
        return httpx.Response(
            201,
            json={
                "status": "CREATED",
                "articleId": "article-1",
                "canonicalUrl": "https://www.dailymirror.lk/story",
            },
        )

    with BackendIngestionClient(
        settings(),
        transport=httpx.MockTransport(handler),
    ) as client:
        result = client.submit(article())

    assert result.status is SubmissionStatus.CREATED
    assert result.article_id == "article-1"


def test_handles_duplicate_response() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={
                "status": "DUPLICATE",
                "articleId": "article-1",
                "canonicalUrl": "https://www.dailymirror.lk/story",
                "duplicateReason": "CONTENT_DUPLICATE",
            },
        )
    )
    with BackendIngestionClient(settings(), transport=transport) as client:
        result = client.submit(article())
    assert result.status is SubmissionStatus.DUPLICATE
    assert result.duplicate_reason is DuplicateReason.CONTENT_DUPLICATE


def test_submits_sinhala_unicode_for_ada_derana() -> None:
    sinhala = article().model_copy(
        update={
            "source_slug": "ada-derana-sinhala",
            "title": "ශ්‍රී ලංකාවේ පුවත",
            "original_language": Language.SINHALA,
            "article_text": "සිංහල අන්තර්ගතය",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read())
        assert payload["sourceSlug"] == "ada-derana-sinhala"
        assert payload["originalLanguage"] == "si"
        assert payload["title"] == "ශ්‍රී ලංකාවේ පුවත"
        assert payload["extractedContent"] == "සිංහල අන්තර්ගතය"
        return httpx.Response(
            200,
            json={
                "status": "DUPLICATE",
                "articleId": "article-si",
                "canonicalUrl": str(sinhala.canonical_url),
            },
        )

    with BackendIngestionClient(settings(), transport=httpx.MockTransport(handler)) as client:
        result = client.submit(sinhala)

    assert result.status is SubmissionStatus.DUPLICATE


def test_maps_backend_validation_and_service_failures() -> None:
    validation_transport = httpx.MockTransport(
        lambda _request: httpx.Response(400, json={"message": "Request validation failed."})
    )
    with (
        BackendIngestionClient(settings(), transport=validation_transport) as client,
        pytest.raises(BackendValidationError, match="validation failed"),
    ):
        client.submit(article())

    service_transport = httpx.MockTransport(
        lambda _request: httpx.Response(503, json={"message": "Service unavailable."})
    )
    with (
        BackendIngestionClient(settings(), transport=service_transport) as client,
        pytest.raises(BackendServiceError, match="Service unavailable"),
    ):
        client.submit(article())


def test_maps_backend_network_failure() -> None:
    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with (
        BackendIngestionClient(
            settings(),
            transport=httpx.MockTransport(unavailable),
        ) as client,
        pytest.raises(BackendUnavailableError),
    ):
        client.submit(article())


def test_heartbeat_404_raises_not_found_error() -> None:
    """404 from heartbeat means the run is gone — this must be a fatal error, not transient."""
    from ingestion.backend import BackendNotFoundError

    transport = httpx.MockTransport(
        lambda _request: httpx.Response(404, json={"message": "IngestionRun was not found."})
    )
    with (
        BackendIngestionClient(settings(), transport=transport) as client,
        pytest.raises(BackendNotFoundError, match="IngestionRun was not found"),
    ):
        client.heartbeat("nonexistent-run-id")


def test_heartbeat_409_raises_validation_error() -> None:
    """409 from heartbeat means lease conflict — this must be a fatal error."""
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(409, json={"message": "Lease conflict."})
    )
    with (
        BackendIngestionClient(settings(), transport=transport) as client,
        pytest.raises(BackendValidationError, match="Lease conflict"),
    ):
        client.heartbeat("conflicted-run-id")


def test_heartbeat_503_raises_service_error() -> None:
    """5xx from heartbeat is a transient error — the worker should retry."""
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(503, json={"message": "Service unavailable."})
    )
    with (
        BackendIngestionClient(settings(), transport=transport) as client,
        pytest.raises(BackendServiceError, match="Service unavailable"),
    ):
        client.heartbeat("some-run-id")

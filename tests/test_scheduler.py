from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from ingestion.backend.models import IngestionTriggerType
from ingestion.config.settings import Settings
from ingestion.runner import RunSummary
from ingestion.scheduler import run_scheduled_job, start_scheduler


@patch("ingestion.scheduler.threading.Thread")
@patch("ingestion.scheduler.BlockingScheduler")
def test_start_scheduler_spawns_threads(
    mock_scheduler_class: MagicMock, mock_thread_class: MagicMock
) -> None:
    settings = Settings(scheduler_enabled=True, api_key=SecretStr("test"))
    mock_adapter_factory = MagicMock()

    mock_scheduler_instance = MagicMock()
    mock_scheduler_class.return_value = mock_scheduler_instance

    mock_thread_instance = MagicMock()
    mock_thread_class.return_value = mock_thread_instance

    start_scheduler(mock_adapter_factory, settings)

    assert mock_thread_class.call_count == 2
    assert mock_thread_instance.start.call_count == 2
    mock_scheduler_instance.start.assert_called_once()


def test_start_scheduler_disabled_does_nothing() -> None:
    settings = Settings(scheduler_enabled=False, api_key=SecretStr("test"))
    mock_adapter_factory = MagicMock()

    with patch("ingestion.scheduler.BlockingScheduler") as mock_scheduler_class:
        start_scheduler(mock_adapter_factory, settings)
        mock_scheduler_class.assert_not_called()


@patch("ingestion.scheduler.time.perf_counter", side_effect=[100.0, 102.4])
@patch("ingestion.scheduler.threading.Thread")
@patch("ingestion.scheduler.run_once")
@patch("ingestion.scheduler.HttpFetcher")
@patch("ingestion.scheduler.BackendIngestionClient")
def test_scheduled_cycle_logs_duration_counters_and_source_failure(
    backend_client_class: MagicMock,
    fetcher_class: MagicMock,
    run_once_mock: MagicMock,
    thread_class: MagicMock,
    _perf_counter: MagicMock,
    caplog: object,
) -> None:
    settings = Settings(api_key=SecretStr("test"))
    backend_client = backend_client_class.return_value.__enter__.return_value
    backend_client.claim.return_value = MagicMock(claimed=True, run_id="run-1")
    fetcher = fetcher_class.return_value.__enter__.return_value
    adapter_factory = MagicMock()
    adapter_factory.return_value = MagicMock()
    heartbeat_thread = thread_class.return_value
    run_once_mock.return_value = RunSummary(
        discovered=23,
        processed=7,
        created=3,
        duplicates=2,
        failed=2,
    )

    caplog.set_level("INFO", logger="ingestion.scheduler.newswire")  # type: ignore[attr-defined]

    run_scheduled_job(
        "newswire",
        adapter_factory,
        settings,
        trigger_type=IngestionTriggerType.SCHEDULED,
    )

    messages = [record.getMessage() for record in caplog.records]  # type: ignore[attr-defined]
    assert "ingestion_cycle_started source=newswire" in messages
    completion = next(
        message for message in messages if message.startswith("ingestion_cycle_completed ")
    )
    assert "duration_seconds=2.400" in completion
    assert "sources_processed=1" in completion
    assert "articles_discovered=23" in completion
    assert "articles_submitted=7" in completion
    assert "failed_sources=1" in completion
    heartbeat_thread.start.assert_called_once()
    heartbeat_thread.join.assert_called_once_with(timeout=2.0)
    backend_client.complete.assert_called_once()
    backend_client.fail.assert_not_called()
    adapter_factory.assert_called_once_with("newswire", fetcher, settings)

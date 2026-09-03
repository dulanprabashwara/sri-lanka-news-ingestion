from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from ingestion.config.settings import Settings
from ingestion.scheduler import start_scheduler


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

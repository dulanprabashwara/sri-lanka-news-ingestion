from unittest.mock import MagicMock

from pydantic import SecretStr

from ingestion.config.settings import Settings
from ingestion.scheduler import start_scheduler


def test_start_scheduler_registers_only_provided_sources() -> None:
    settings = Settings(scheduler_enabled=True, api_key=SecretStr("test"))
    mock_adapter_factory = MagicMock()

    # We will patch BlockingScheduler to mock add_job
    import ingestion.scheduler

    original_scheduler = ingestion.scheduler.BlockingScheduler  # type: ignore[attr-defined]

    mock_scheduler_instance = MagicMock()
    mock_scheduler_class = MagicMock(return_value=mock_scheduler_instance)

    ingestion.scheduler.BlockingScheduler = mock_scheduler_class  # type: ignore[attr-defined]

    try:
        sources = ["daily-mirror", "newsfirst"]
        start_scheduler(sources, mock_adapter_factory, settings)

        assert mock_scheduler_instance.add_job.call_count == 2

        args_list = mock_scheduler_instance.add_job.call_args_list
        registered_slugs = []
        for call in args_list:
            job_args = call.kwargs.get("args", [])
            if job_args:
                registered_slugs.append(job_args[0])

        assert "daily-mirror" in registered_slugs
        assert "newsfirst" in registered_slugs
        assert "ada-derana-sinhala" not in registered_slugs
    finally:
        ingestion.scheduler.BlockingScheduler = original_scheduler  # type: ignore[attr-defined]

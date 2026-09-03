import pytest
from pydantic import SecretStr, ValidationError

from ingestion.config.settings import Settings


def test_scheduler_interval_minutes_validation() -> None:
    # 10 minutes -> valid (default)
    settings = Settings(api_key=SecretStr("test"))
    assert settings.scheduler_interval_minutes == 10

    # 5 minutes -> valid
    settings = Settings(scheduler_interval_minutes=5, api_key=SecretStr("test"))
    assert settings.scheduler_interval_minutes == 5

    # 4 minutes -> invalid
    with pytest.raises(ValidationError) as exc:
        Settings(scheduler_interval_minutes=4, api_key=SecretStr("test"))

    assert "Input should be greater than or equal to 5" in str(exc.value)

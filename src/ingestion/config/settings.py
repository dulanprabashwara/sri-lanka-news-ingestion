from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime settings loaded from INGESTION_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="INGESTION_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    http_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    http_max_redirects: int = Field(default=5, ge=0, le=20)
    http_user_agent: str = Field(
        default=(
            "SriLankaNewsIngestion/0.1 "
            "(+https://github.com/dulanprabashwara/sri-lanka-news-ingestion)"
        ),
        min_length=10,
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime settings loaded from INGESTION_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="INGESTION_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True,
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
    backend_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8080")
    api_key: SecretStr
    daily_mirror_feed_url: AnyHttpUrl = AnyHttpUrl(
        "https://www.dailymirror.lk/rss/breaking_news/108"
    )
    newsfirst_listing_url: AnyHttpUrl = AnyHttpUrl("https://www.newsfirst.lk/latest")
    hiru_news_sinhala_listing_url: AnyHttpUrl = AnyHttpUrl("https://www.hirunews.lk/")
    ada_derana_sinhala_feed_url: AnyHttpUrl = AnyHttpUrl("https://sinhala.adaderana.lk/rss.php")
    ada_derana_sinhala_homepage_url: AnyHttpUrl = AnyHttpUrl("https://sinhala.adaderana.lk/")
    the_island_feed_url: AnyHttpUrl = AnyHttpUrl("http://island.lk/feed/")
    divaina_feed_url: AnyHttpUrl = AnyHttpUrl("https://www.divaina.lk/feed")
    lankadeepa_listing_url: AnyHttpUrl = AnyHttpUrl("https://www.lankadeepa.lk/latest-news/1")
    run_limit: int = Field(default=3, ge=1, le=20)
    scheduler_enabled: bool = False
    scheduler_interval_minutes: int = Field(default=10, ge=5)
    scheduler_jitter_seconds: int = Field(default=120, ge=0)
    lease_duration_seconds: int = Field(default=600, ge=60)
    heartbeat_interval_seconds: int = Field(default=120, ge=30)

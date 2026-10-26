"""Configuration and environment settings."""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Urja Meter Ops API"
    app_version: str = "1.0.0"
    app_env: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    # Upstream Portal Configuration
    urja_base_url: str = "https://urja-ops.flockenergy.tech"
    urja_username: str = ""
    urja_password: str = ""
    upstream_timeout_seconds: float = 15.0
    upstream_max_retries: int = 1

    # Local Fixture / Mock Mode for testing without live portal access
    mock_mode: bool = False

    # Optional API key for public API protection if enabled
    api_key: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached singleton instance of Settings."""
    return Settings()

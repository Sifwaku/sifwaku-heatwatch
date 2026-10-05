"""
Application configuration loaded from environment variables.
Never hard-code API keys.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite:///./data/sifwaku_heatwatch.db"

    # API keys (optional; empty = provider unavailable until key is set)
    openweathermap_api_key: str = ""
    visualcrossing_api_key: str = ""

    # App
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # Default location — Lusaka, Zambia
    default_latitude: float = -15.4167
    default_longitude: float = 28.2833
    default_location_name: str = "Lusaka"
    default_country: str = "Zambia"


@lru_cache
def get_settings() -> Settings:
    return Settings()

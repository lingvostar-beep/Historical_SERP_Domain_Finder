from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    app_host: str = "127.0.0.1"
    app_port: int = 8872
    app_basic_user: str = "admin"
    app_basic_password: str = "change-me"

    database_url: str = "postgresql+psycopg://hsdf:hsdf@127.0.0.1:5433/hsdf"
    redis_url: str = "redis://127.0.0.1:6380/0"

    dataforseo_login: str = ""
    dataforseo_password: str = ""
    dataforseo_max_history_days: int = 365
    dataforseo_primary_source: str = "dataforseo_google_current"
    dataforseo_reference_price_per_snapshot: float = 0.00012
    dataforseo_concurrency: int = 5
    dataforseo_max_retries: int = 3  # automatic attempts on 429/5xx/timeout
    dataforseo_retry_base_seconds: float = 1.0

    whoisfreaks_api_key: str = ""
    whoisfreaks_cache_ttl_hours: int = 24
    whoisfreaks_reference_usd_per_credit: float = 0.004
    # TZ §15.9 — bulk RPM depends on plan (5k pack ≈ 8 rpm, 50k ≈ 20 rpm)
    whoisfreaks_bulk_rpm: float = 8.0
    whoisfreaks_max_retries: int = 3
    whoisfreaks_retry_base_seconds: float = 1.0

    godaddy_pat: str = ""
    godaddy_api_base: str = "https://api.godaddy.com"

    raw_storage_dir: Path = Field(default=ROOT / "data" / "raw")
    locations_cache_path: Path = Field(default=ROOT / "data" / "cache" / "locations_and_languages.json")
    locations_cache_ttl_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()

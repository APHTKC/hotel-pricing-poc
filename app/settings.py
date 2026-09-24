from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Luxury Hotel Pricing Intelligence System"
    demo_mode: bool = False
    storage_backend: str = "local"
    local_data_path: Path = Path("data/rates.jsonl")
    google_sheet_id: str = ""
    google_service_account_json: str = ""
    job_token: str = "change-me"
    base_currency: str = "TWD"
    log_level: str = "INFO"
    lead_days: str = "1,7,14,30,60,90"
    booking_com_api_key: str = ""
    booking_com_affiliate_id: str = ""
    ota_config_path: Path = Path("config/ota-properties.yaml")
    ota_booker_country: str = "tw"
    adapter_health_path: Path = Path("data/adapter_health.json")
    diagnostic_snapshot_dir: Path = Path("data/diagnostics")
    backoff_failure_threshold: int = 2
    backoff_base_minutes: int = 360
    backoff_blocked_base_minutes: int = 1440
    backoff_max_minutes: int = 10080

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

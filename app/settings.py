from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Luxury Hotel Pricing Intelligence System"
    demo_mode: bool = True
    storage_backend: str = "local"
    local_data_path: Path = Path("data/rates.jsonl")
    google_sheet_id: str = ""
    google_service_account_json: str = ""
    job_token: str = "change-me"
    base_currency: str = "TWD"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

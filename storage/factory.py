from app.settings import Settings
from storage.base import RateStore
from storage.google_sheets import GoogleSheetsStore
from storage.local_jsonl import LocalJsonlStore


def get_store(settings: Settings) -> RateStore:
    if settings.storage_backend == "google_sheets":
        if not settings.google_sheet_id or not settings.google_service_account_json:
            raise ValueError("Google Sheets storage requires GOOGLE_SHEET_ID and GOOGLE_SERVICE_ACCOUNT_JSON")
        return GoogleSheetsStore(settings.google_sheet_id, settings.google_service_account_json)
    return LocalJsonlStore(settings.local_data_path)

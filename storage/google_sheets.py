import json

import gspread
from google.oauth2.service_account import Credentials

from app.models import RateObservation
from storage.base import RateStore


SHEET_COLUMNS = [
    "schema_version", "observation_id", "queried_at", "check_in", "check_out",
    "lead_days", "nights", "adults", "hotel_id", "hotel_name", "city",
    "room_type_code", "room_type_name", "room_size_sqm", "size_band",
    "rate_plan_code", "rate_plan_name", "breakfast_included",
    "cancellation_policy", "price_before_tax", "service_charge", "tax",
    "total_price", "currency", "fx_rate_to_twd", "total_twd",
    "price_per_sqm", "cpi_index", "cpi_base_index", "cpi_adjusted_twd",
    "source_url", "status",
]


class GoogleSheetsStore(RateStore):
    def __init__(self, sheet_id: str, service_account_json: str):
        info = json.loads(service_account_json)
        credentials = Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        self.workbook = gspread.authorize(credentials).open_by_key(sheet_id)
        try:
            self.sheet = self.workbook.worksheet("rates")
        except gspread.WorksheetNotFound:
            self.sheet = self.workbook.add_worksheet(title="rates", rows=1000, cols=len(SHEET_COLUMNS))
            self.sheet.append_row(SHEET_COLUMNS)

    def append(self, rows: list[RateObservation]) -> int:
        values = []
        for row in rows:
            data = row.model_dump(mode="json")
            values.append(["" if data.get(column) is None else str(data.get(column)) for column in SHEET_COLUMNS])
        if values:
            self.sheet.append_rows(values, value_input_option="RAW")
        return len(values)

    def read_all(self) -> list[RateObservation]:
        records = self.sheet.get_all_records()
        base_fields = set(RateObservation.model_fields)
        return [RateObservation.model_validate({k: v for k, v in record.items() if k in base_fields}) for record in records]

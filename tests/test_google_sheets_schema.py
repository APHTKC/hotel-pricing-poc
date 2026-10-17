from storage.google_sheets import GoogleSheetsStore, SHEET_COLUMNS, model_payload


def test_google_sheet_schema_preserves_all_natural_key_dimensions():
    for column in (
        "source_platform",
        "check_out",
        "rooms",
        "adults",
        "children",
        "currency",
    ):
        assert column in SHEET_COLUMNS


def test_google_sheet_schema_preserves_tax_inclusion_for_parity():
    assert "tax_inclusion" in SHEET_COLUMNS


def test_legacy_blank_dimensions_are_omitted_to_apply_model_defaults():
    payload = model_payload(
        {
            "hotel_id": "hotel",
            "rooms": "",
            "adults": 2,
            "children": "",
            "source_platform": "",
            "unrelated": "ignored",
        }
    )

    assert payload == {"hotel_id": "hotel", "adults": 2}


def test_existing_sheet_column_order_is_preserved_when_schema_expands():
    class FakeSheet:
        def __init__(self):
            self.header = ["observation_id", "hotel_id", "currency"]

        def row_values(self, row):
            assert row == 1
            return list(self.header)

        def update_cell(self, row, column, value):
            assert row == 1
            assert column == len(self.header) + 1
            self.header.append(value)

    store = GoogleSheetsStore.__new__(GoogleSheetsStore)
    store.sheet = FakeSheet()

    store._ensure_columns()

    assert store.columns[:3] == ["observation_id", "hotel_id", "currency"]
    assert set(store.columns) == set(SHEET_COLUMNS)

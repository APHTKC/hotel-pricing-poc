import ast
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

import pytest


SCHEMA_PATH = Path("public/export-schema.json")
ALLOWED_FIELD_TYPES = {"string", "date", "datetime", "integer", "number", "boolean"}


@pytest.fixture(scope="module")
def export_schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def duplicate_values(values):
    return sorted(value for value, count in Counter(values).items() if count > 1)


def page_csv_columns(path):
    html = path.read_text(encoding="utf-8")
    match = re.search(r"const columns=(\[[^\]]+\]),csv=", html)
    assert match, f"Could not find the CSV columns array in {path}"
    return ast.literal_eval(match.group(1))


def test_csv_columns_are_unique_defined_and_match_pages(export_schema):
    csv_columns = export_schema["csv_columns"]
    assert set(csv_columns) == {"latest", "history"}, (
        f"Unexpected csv_columns outputs: {sorted(csv_columns)}"
    )

    definitions = export_schema["field_definitions"]
    pages = {
        "latest": Path("public/index.html"),
        "history": Path("public/history.html"),
    }
    for output, columns in csv_columns.items():
        duplicates = duplicate_values(columns)
        assert not duplicates, f"{output} CSV has duplicate columns: {duplicates}"

        missing = [field for field in columns if field not in definitions]
        assert not missing, (
            f"{output} CSV columns missing field_definitions: {missing}"
        )
        assert columns == page_csv_columns(pages[output]), (
            f"{output} page CSV columns differ from export-schema.json"
        )


def test_field_groups_are_unique_complete_and_non_overlapping(export_schema):
    definitions = export_schema["field_definitions"]
    groups = export_schema["field_groups"]

    group_keys = [group["key"] for group in groups]
    duplicate_keys = duplicate_values(group_keys)
    assert not duplicate_keys, f"Duplicate field_group keys: {duplicate_keys}"

    memberships = defaultdict(list)
    for group in groups:
        fields = group["fields"]
        duplicates = duplicate_values(fields)
        assert not duplicates, (
            f"field_group {group['key']!r} has duplicate fields: {duplicates}"
        )
        missing = [field for field in fields if field not in definitions]
        assert not missing, (
            f"field_group {group['key']!r} fields missing definitions: {missing}"
        )
        for field in fields:
            memberships[field].append(group["key"])

    exported_fields = {
        field
        for columns in export_schema["csv_columns"].values()
        for field in columns
    }
    wrong_memberships = {
        field: memberships.get(field, [])
        for field in sorted(exported_fields)
        if len(memberships.get(field, [])) != 1
    }
    assert not wrong_memberships, (
        "CSV fields must belong to exactly one field_group: "
        f"{wrong_memberships}"
    )

    ungrouped_definitions = sorted(set(definitions) - set(memberships))
    assert not ungrouped_definitions, (
        f"field_definitions missing from field_groups: {ungrouped_definitions}"
    )


def test_field_definition_value_contracts(export_schema):
    for field, definition in export_schema["field_definitions"].items():
        field_type = definition.get("type")
        assert field_type in ALLOWED_FIELD_TYPES, (
            f"Field {field!r} has unsupported type {field_type!r}"
        )
        assert type(definition.get("nullable")) is bool, (
            f"Field {field!r} nullable must be a boolean"
        )
        assert type(definition.get("unknown_allowed")) is bool, (
            f"Field {field!r} unknown_allowed must be a boolean"
        )


def test_scope_keys_are_unique_and_described(export_schema):
    scopes = export_schema["scopes"]
    scope_keys = [scope.get("key") for scope in scopes]
    duplicate_keys = duplicate_values(scope_keys)
    assert not duplicate_keys, f"Duplicate scope keys: {duplicate_keys}"

    for index, scope in enumerate(scopes):
        assert isinstance(scope.get("key"), str) and scope["key"].strip(), (
            f"Scope at index {index} has an invalid key: {scope.get('key')!r}"
        )
        assert isinstance(scope.get("applies_to"), str) and scope["applies_to"].strip(), (
            f"Scope {scope['key']!r} has an invalid applies_to description"
        )

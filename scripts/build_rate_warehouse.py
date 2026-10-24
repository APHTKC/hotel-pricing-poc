"""Build verified monthly Parquet mirrors from the authoritative JSONL shards."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import duckdb

from services.deduplication import observation_natural_key
from storage.local_jsonl import iter_jsonl_records, jsonl_partition_paths


SOURCE = Path("data/rates")
OTA_BROWSER_SOURCE = Path("data/ota_browser_snapshots.jsonl")
TARGET_DIR = Path("data/warehouse/rates")
MANIFEST_TARGET = Path("data/warehouse/manifest.json")


def _sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parquet_keys(connection: duckdb.DuckDBPyConnection, path: Path) -> set[tuple[str, ...]]:
    cursor = connection.execute(f"SELECT * FROM read_parquet('{_sql_path(path)}')")
    columns = [item[0] for item in cursor.description]
    keys: set[tuple[str, ...]] = set()
    while batch := cursor.fetchmany(10_000):
        keys.update(observation_natural_key(dict(zip(columns, row))) for row in batch)
    return keys


def build_rate_warehouse(
    source: Path = SOURCE,
    target_dir: Path = TARGET_DIR,
    manifest_target: Path = MANIFEST_TARGET,
    extra_sources: tuple[Path, ...] = (),
) -> dict:
    shards = jsonl_partition_paths(source)
    if not shards:
        raise ValueError(f"No JSONL rate shards found under {source}")

    by_month: dict[str, list[Path]] = defaultdict(list)
    for shard in shards:
        month = shard.parent.name if shard.parent != source else shard.stem[:7]
        if len(month) != 7:
            raise ValueError(f"Cannot determine month for {shard}")
        by_month[month].append(shard)
    extra_paths = [path for path in extra_sources if path.exists()]
    for extra in extra_paths:
        for row in iter_jsonl_records(extra):
            queried_at = str(row.get("queried_at") or "")
            if len(queried_at) >= 7:
                by_month.setdefault(queried_at[:7], [])

    target_dir.mkdir(parents=True, exist_ok=True)
    expected = {f"{month}.parquet" for month in by_month}
    for stale in target_dir.glob("*.parquet"):
        if stale.name not in expected:
            stale.unlink()

    connection = duckdb.connect()
    partitions = []
    all_source_keys: set[tuple[str, ...]] = set()
    all_parquet_keys: set[tuple[str, ...]] = set()
    source_rows = 0
    parquet_rows = 0
    try:
        for month in sorted(by_month):
            month_shards = sorted(by_month[month])
            input_paths = [*month_shards, *extra_paths]
            month_source_keys: set[tuple[str, ...]] = set()
            month_source_rows = 0
            for shard in input_paths:
                for row in iter_jsonl_records(shard):
                    if str(row.get("queried_at") or "")[:7] != month:
                        continue
                    month_source_rows += 1
                    month_source_keys.add(observation_natural_key(row))

            temp_target = target_dir / f".{month}.parquet.tmp"
            final_target = target_dir / f"{month}.parquet"
            if temp_target.exists():
                temp_target.unlink()
            files = [str(path.resolve()) for path in input_paths]
            connection.execute(
                "CREATE OR REPLACE TEMP TABLE month_rates_raw AS "
                "SELECT * FROM read_json_auto(?, format='newline_delimited', "
                "union_by_name=true, sample_size=-1) "
                "WHERE substr(cast(queried_at AS VARCHAR), 1, 7) = ?",
                [files, month],
            )
            raw_columns = {
                row[0]
                for row in connection.execute("DESCRIBE month_rates_raw").fetchall()
            }
            if "nights" not in raw_columns:
                connection.execute("ALTER TABLE month_rates_raw ADD COLUMN nights INTEGER")
            if "nightly_adr_twd" not in raw_columns:
                connection.execute(
                    "ALTER TABLE month_rates_raw ADD COLUMN nightly_adr_twd DOUBLE"
                )
            if "total_twd" not in raw_columns:
                connection.execute("ALTER TABLE month_rates_raw ADD COLUMN total_twd DOUBLE")
            if "total_price" not in raw_columns:
                connection.execute("ALTER TABLE month_rates_raw ADD COLUMN total_price DOUBLE")
            if "tax_inclusion" not in raw_columns:
                connection.execute(
                    "ALTER TABLE month_rates_raw ADD COLUMN tax_inclusion VARCHAR"
                )
            if "breakfast_included" not in raw_columns:
                connection.execute(
                    "ALTER TABLE month_rates_raw ADD COLUMN breakfast_included BOOLEAN"
                )
            if "rate_plan_name" not in raw_columns:
                connection.execute(
                    "ALTER TABLE month_rates_raw ADD COLUMN rate_plan_name VARCHAR"
                )
            if "source_method" not in raw_columns:
                connection.execute(
                    "ALTER TABLE month_rates_raw ADD COLUMN source_method VARCHAR"
                )
            if "source_url" not in raw_columns:
                connection.execute(
                    "ALTER TABLE month_rates_raw ADD COLUMN source_url VARCHAR"
                )
            for column in ("price_before_tax", "service_charge", "tax"):
                if column not in raw_columns:
                    connection.execute(
                        f"ALTER TABLE month_rates_raw ADD COLUMN {column} DOUBLE"
                    )
            connection.execute(
                "CREATE OR REPLACE TEMP TABLE month_rates AS "
                "SELECT * REPLACE ("
                "coalesce("
                "  try_cast(nights AS INTEGER), "
                "  date_diff('day', try_cast(check_in AS DATE), try_cast(check_out AS DATE))"
                ") AS nights, "
                "coalesce("
                "  try_cast(nightly_adr_twd AS DOUBLE), "
                "  try_cast(coalesce(total_twd, total_price) AS DOUBLE) / nullif("
                "    coalesce("
                "      try_cast(nights AS INTEGER), "
                "      date_diff('day', try_cast(check_in AS DATE), try_cast(check_out AS DATE))"
                "    ), 0"
                "  )"
                ") AS nightly_adr_twd, "
                "CASE "
                "  WHEN coalesce(nullif(trim(cast(tax_inclusion AS VARCHAR)), ''), 'unknown') "
                "       <> 'unknown' "
                "    THEN cast(tax_inclusion AS VARCHAR) "
                "  WHEN hotel_id = 'capella_taipei' "
                "   AND source_platform = 'official' "
                "   AND (source_method = 'public_booking_page' "
                "        OR source_url LIKE '%Hotel=47696%') "
                "    THEN 'included' "
                "  WHEN hotel_id = 'grand_hotel_taipei' "
                "   AND source_platform = 'official' "
                "   AND source_url LIKE '%/webhotel-v5/1071%' "
                "    THEN 'included' "
                "  WHEN price_before_tax IS NOT NULL "
                "   AND (service_charge IS NOT NULL OR tax IS NOT NULL) "
                "   AND coalesce(total_price, total_twd) IS NOT NULL "
                "   AND abs("
                "     try_cast(coalesce(total_price, total_twd) AS DOUBLE) - "
                "     (try_cast(price_before_tax AS DOUBLE) + "
                "      coalesce(try_cast(service_charge AS DOUBLE), 0) + "
                "      coalesce(try_cast(tax AS DOUBLE), 0))"
                "   ) <= greatest("
                "     1.0, abs(try_cast(coalesce(total_price, total_twd) AS DOUBLE)) * 0.0001"
                "   ) "
                "    THEN 'included' "
                "  ELSE 'unknown' "
                "END AS tax_inclusion, "
                "coalesce(try_cast(breakfast_included AS BOOLEAN), CASE "
                "  WHEN regexp_matches(lower(coalesce(cast(rate_plan_name AS VARCHAR), '')), "
                "       '(不含|無)[^｜|]{0,12}早餐') "
                "    OR lower(coalesce(cast(rate_plan_name AS VARCHAR), '')) LIKE '%不含早%' "
                "    OR lower(coalesce(cast(rate_plan_name AS VARCHAR), '')) LIKE '%不含餐食%' "
                "    OR lower(coalesce(cast(rate_plan_name AS VARCHAR), '')) LIKE '%純住宿%' "
                "    OR lower(coalesce(cast(rate_plan_name AS VARCHAR), '')) LIKE '%breakfast not included%' "
                "    OR lower(coalesce(cast(rate_plan_name AS VARCHAR), '')) LIKE '%room only%' "
                "    THEN false "
                "  WHEN regexp_matches(lower(coalesce(cast(rate_plan_name AS VARCHAR), '')), "
                "       '含[^｜|]{0,12}早餐') "
                "    OR lower(coalesce(cast(rate_plan_name AS VARCHAR), '')) LIKE '%含早%' "
                "    OR lower(coalesce(cast(rate_plan_name AS VARCHAR), '')) LIKE '%早餐專案%' "
                "    OR lower(coalesce(cast(rate_plan_name AS VARCHAR), '')) LIKE '%breakfast included%' "
                "    OR lower(coalesce(cast(rate_plan_name AS VARCHAR), '')) LIKE '%with breakfast%' "
                "    THEN true "
                "  ELSE NULL "
                "END) AS breakfast_included"
                ") FROM month_rates_raw"
            )
            connection.execute(
                f"COPY (SELECT * FROM month_rates ORDER BY queried_at, observation_id) "
                f"TO '{_sql_path(temp_target)}' "
                "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 10000)"
            )
            month_parquet_rows = connection.execute(
                f"SELECT count(*) FROM read_parquet('{_sql_path(temp_target)}')"
            ).fetchone()[0]
            month_parquet_keys = _parquet_keys(connection, temp_target)
            if month_parquet_rows != month_source_rows:
                temp_target.unlink(missing_ok=True)
                raise ValueError(
                    f"Row count mismatch for {month}: JSONL={month_source_rows}, "
                    f"Parquet={month_parquet_rows}"
                )
            if month_parquet_keys != month_source_keys:
                temp_target.unlink(missing_ok=True)
                raise ValueError(f"Natural key mismatch for {month}")
            temp_target.replace(final_target)

            source_rows += month_source_rows
            parquet_rows += month_parquet_rows
            all_source_keys.update(month_source_keys)
            all_parquet_keys.update(month_parquet_keys)
            partitions.append(
                {
                    "month": month,
                    "path": f"rates/{month}.parquet",
                    "source_shards": len(input_paths),
                    "rows": month_parquet_rows,
                    "natural_keys": len(month_parquet_keys),
                    "bytes": final_target.stat().st_size,
                    "sha256": _sha256(final_target),
                }
            )
    finally:
        connection.close()

    if parquet_rows != source_rows or all_parquet_keys != all_source_keys:
        raise ValueError("Warehouse-wide JSONL/Parquet validation failed")

    manifest = {
        "schema_version": "1.0",
        "sources": [
            str(path).replace("\\", "/")
            for path in (source, *extra_paths)
        ],
        "format": "parquet",
        "query_engine": "duckdb",
        "compression": "zstd",
        "rows": parquet_rows,
        "natural_keys": len(all_parquet_keys),
        "partitions": partitions,
    }
    manifest_target.parent.mkdir(parents=True, exist_ok=True)
    manifest_target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    manifest = build_rate_warehouse(extra_sources=(OTA_BROWSER_SOURCE,))
    print(
        f"Built {len(manifest['partitions'])} Parquet partitions with "
        f"{manifest['rows']} rows and {manifest['natural_keys']} natural keys"
    )


if __name__ == "__main__":
    main()

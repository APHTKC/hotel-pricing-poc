"""Build a reproducible DuckDB quality profile from the Parquet rate mirror."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import duckdb

from services.rate_parity import (
    normalize_cancellation_class,
    normalize_cancellation_deadline,
    normalize_cancellation_schedule,
)


PARQUET_GLOB = Path("data/warehouse/rates/*.parquet")
MANIFEST_SOURCE = Path("data/warehouse/manifest.json")
TARGET = Path("data/warehouse/analysis.json")
PUBLIC_TARGET = Path("public/data/warehouse_quality.json")


def _sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def public_quality_payload(payload: dict) -> dict:
    """Return the compact, non-sensitive quality summary used by the site."""

    return {
        "schema_version": "1.0",
        "rows": payload["rows"],
        "hotels": payload["hotels"],
        "queried_at": payload["queried_at"],
        "quality": payload["quality"],
        "sources": payload["sources"],
        "top_tax_gaps": [
            {
                "hotel_id": item["hotel_id"],
                "rows": item["rows"],
                "known_tax_rows": item["known_tax_rows"],
                "unknown_tax_rows": item["unknown_tax_rows"],
            }
            for item in payload["hotels_by_unknown_tax"][:10]
            if item["unknown_tax_rows"] > 0
        ],
        "unresolved_cancellation_rows": sum(
            item["rows"] for item in payload["unknown_cancellation_policies"]
        ),
        "unresolved_cancellation_groups": len(
            payload["unknown_cancellation_policies"]
        ),
    }


def build_warehouse_analysis(
    parquet_glob: Path = PARQUET_GLOB,
    manifest_source: Path = MANIFEST_SOURCE,
    target: Path = TARGET,
) -> dict:
    manifest = json.loads(manifest_source.read_text(encoding="utf-8"))
    connection = duckdb.connect()
    try:
        connection.execute(
            f"CREATE TEMP VIEW rates AS SELECT * FROM read_parquet("
            f"'{_sql_path(parquet_glob)}', union_by_name=true)"
        )
        summary_row = connection.execute(
            """
            SELECT
                count(*) AS rows,
                count(DISTINCT hotel_id) AS hotels,
                min(cast(queried_at AS VARCHAR)) AS queried_at_min,
                max(cast(queried_at AS VARCHAR)) AS queried_at_max,
                count_if(room_size_sqm IS NOT NULL) AS known_room_size_rows,
                count_if(coalesce(tax_inclusion, 'unknown') <> 'unknown') AS known_tax_rows,
                count_if(
                    cancellation_policy IS NOT NULL
                    AND trim(cancellation_policy) <> ''
                ) AS known_cancellation_policy_rows,
                count_if(nightly_adr_twd IS NOT NULL) AS nightly_adr_rows
            FROM rates
            """
        ).fetchone()
        columns = [item[0] for item in connection.description]
        summary = dict(zip(columns, summary_row))

        source_rows = connection.execute(
            """
            SELECT
                coalesce(source_platform, 'unknown') AS source_platform,
                count(*) AS rows,
                count(DISTINCT hotel_id) AS hotels,
                count_if(room_size_sqm IS NOT NULL) AS known_room_size_rows,
                count_if(coalesce(tax_inclusion, 'unknown') <> 'unknown') AS known_tax_rows,
                count_if(
                    cancellation_policy IS NOT NULL
                    AND trim(cancellation_policy) <> ''
                ) AS known_cancellation_policy_rows
            FROM rates
            GROUP BY 1
            ORDER BY 1
            """
        ).fetchall()
        source_columns = [item[0] for item in connection.description]

        cancellation_rows = connection.execute(
            """
            SELECT
                hotel_id,
                coalesce(source_platform, 'unknown') AS source_platform,
                cancellation_policy,
                cast(check_in AS VARCHAR) AS check_in
            FROM rates
            """
        ).fetchall()

        hotel_rows = connection.execute(
            """
            SELECT
                hotel_id,
                count(*) AS rows,
                count_if(room_size_sqm IS NOT NULL) AS known_room_size_rows,
                count_if(coalesce(tax_inclusion, 'unknown') <> 'unknown') AS known_tax_rows,
                count_if(room_size_sqm IS NULL) AS unknown_room_size_rows
            FROM rates
            GROUP BY hotel_id
            ORDER BY unknown_room_size_rows DESC, hotel_id
            """
        ).fetchall()
        hotel_columns = [item[0] for item in connection.description]
    finally:
        connection.close()

    if summary["rows"] != manifest["rows"]:
        raise ValueError(
            f"Warehouse analysis row mismatch: manifest={manifest['rows']}, "
            f"parquet={summary['rows']}"
        )

    row_count = int(summary["rows"])
    room_size = int(summary["known_room_size_rows"])
    known_tax = int(summary["known_tax_rows"])
    known_cancel = int(summary["known_cancellation_policy_rows"])
    nightly_adr = int(summary["nightly_adr_rows"])
    cancellation_class_counts: Counter[str] = Counter()
    cancellation_deadline_counts: Counter[str] = Counter()
    cancellation_schedule_counts: Counter[str] = Counter()
    structured_cancellation_schedules: Counter[tuple[str, str, str, str]] = Counter()
    unknown_cancellation_policies: Counter[tuple[str, str, str]] = Counter()
    for hotel_id, source_platform, policy, check_in in cancellation_rows:
        if normalize_cancellation_class(policy) != "unknown":
            cancellation_class_counts[source_platform] += 1
        elif policy and str(policy).strip():
            unknown_cancellation_policies[
                (hotel_id, source_platform, str(policy).strip())
            ] += 1
        if normalize_cancellation_deadline(
            {"cancellation_policy": policy, "check_in": check_in}
        ) != "unknown":
            cancellation_deadline_counts[source_platform] += 1
        schedule = normalize_cancellation_schedule(policy)
        if schedule:
            cancellation_schedule_counts[source_platform] += 1
            structured_cancellation_schedules[
                (
                    hotel_id,
                    source_platform,
                    str(policy).strip(),
                    json.dumps(schedule, ensure_ascii=False, sort_keys=True),
                )
            ] += 1
    known_cancellation_class = sum(cancellation_class_counts.values())
    known_cancellation_deadline = sum(cancellation_deadline_counts.values())
    known_cancellation_schedule = sum(cancellation_schedule_counts.values())

    sources = [dict(zip(source_columns, row)) for row in source_rows]
    for source in sources:
        source_platform = source["source_platform"]
        source["known_cancellation_class_rows"] = cancellation_class_counts[
            source_platform
        ]
        source["known_cancellation_deadline_rows"] = cancellation_deadline_counts[
            source_platform
        ]
        source["known_cancellation_schedule_rows"] = cancellation_schedule_counts[
            source_platform
        ]

    hotels_by_unknown_room_size = [
        dict(zip(hotel_columns, row)) for row in hotel_rows
    ]
    hotels_by_unknown_tax = []
    for hotel in hotels_by_unknown_room_size:
        item = dict(hotel)
        item["unknown_tax_rows"] = item["rows"] - item["known_tax_rows"]
        hotels_by_unknown_tax.append(item)
    hotels_by_unknown_tax.sort(
        key=lambda item: (-item["unknown_tax_rows"], item["hotel_id"])
    )

    payload = {
        "schema_version": "1.3",
        "input": str(parquet_glob).replace("\\", "/"),
        "manifest_sha256": [
            {"month": item["month"], "sha256": item["sha256"]}
            for item in manifest["partitions"]
        ],
        "rows": row_count,
        "natural_keys": int(manifest["natural_keys"]),
        "hotels": int(summary["hotels"]),
        "queried_at": {
            "min": summary["queried_at_min"],
            "max": summary["queried_at_max"],
        },
        "quality": {
            "known_room_size_rows": room_size,
            "known_room_size_ratio": _ratio(room_size, row_count),
            "known_tax_rows": known_tax,
            "known_tax_ratio": _ratio(known_tax, row_count),
            "known_cancellation_policy_rows": known_cancel,
            "known_cancellation_policy_ratio": _ratio(known_cancel, row_count),
            "known_cancellation_class_rows": known_cancellation_class,
            "known_cancellation_class_ratio": _ratio(
                known_cancellation_class, row_count
            ),
            "known_cancellation_deadline_rows": known_cancellation_deadline,
            "known_cancellation_deadline_ratio": _ratio(
                known_cancellation_deadline, row_count
            ),
            "known_cancellation_schedule_rows": known_cancellation_schedule,
            "known_cancellation_schedule_ratio": _ratio(
                known_cancellation_schedule, row_count
            ),
            "nightly_adr_rows": nightly_adr,
            "nightly_adr_ratio": _ratio(nightly_adr, row_count),
        },
        "sources": sources,
        "hotels_by_unknown_room_size": hotels_by_unknown_room_size,
        "hotels_by_unknown_tax": hotels_by_unknown_tax,
        "unknown_cancellation_policies": [
            {
                "hotel_id": hotel_id,
                "source_platform": source_platform,
                "cancellation_policy": policy,
                "rows": rows,
            }
            for (hotel_id, source_platform, policy), rows in sorted(
                unknown_cancellation_policies.items(),
                key=lambda item: (-item[1], *item[0]),
            )
        ],
        "structured_cancellation_schedules": [
            {
                "hotel_id": hotel_id,
                "source_platform": source_platform,
                "cancellation_policy": policy,
                "schedule": json.loads(schedule_json),
                "rows": rows,
            }
            for (
                hotel_id,
                source_platform,
                policy,
                schedule_json,
            ), rows in sorted(
                structured_cancellation_schedules.items(),
                key=lambda item: (-item[1], *item[0]),
            )
        ],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    payload = build_warehouse_analysis()
    PUBLIC_TARGET.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_TARGET.write_text(
        json.dumps(public_quality_payload(payload), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Profiled {payload['rows']} Parquet rows across "
        f"{payload['hotels']} hotels and {len(payload['sources'])} sources; "
        f"wrote {PUBLIC_TARGET}"
    )


if __name__ == "__main__":
    main()

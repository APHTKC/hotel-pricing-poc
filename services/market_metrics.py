from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from statistics import mean, median
from typing import Any


def _field(row: object, name: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(name)
    return getattr(row, name, None)


def _number(row: object, name: str) -> float | None:
    value = _field(row, name)
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def calculate_market_summary(rows: Iterable[object]) -> dict[str, int | float | None]:
    """Calculate hotel-equal-weighted market indicators.

    The market ADR is the median of each hotel's median ADR. This prevents a
    hotel with more room types or rate plans from dominating the market. The
    function accepts both RateObservation objects and serialized row mappings
    so the API and static-data build use exactly the same implementation.
    """

    observations = list(rows)
    grouped: dict[str, list[object]] = defaultdict(list)
    for row in observations:
        hotel_id = _field(row, "hotel_id")
        if hotel_id:
            grouped[str(hotel_id)].append(row)

    hotel_averages: list[float] = []
    hotel_medians: list[float] = []
    hotel_per_sqm_medians: list[float] = []
    hotel_cpi_medians: list[float] = []
    for hotel_rows in grouped.values():
        totals = [value for row in hotel_rows if (value := _number(row, "total_twd")) is not None]
        per_sqm = [value for row in hotel_rows if (value := _number(row, "price_per_sqm")) is not None]
        cpi = [value for row in hotel_rows if (value := _number(row, "cpi_adjusted_twd")) is not None]
        if totals:
            hotel_averages.append(mean(totals))
            hotel_medians.append(median(totals))
        if per_sqm:
            hotel_per_sqm_medians.append(median(per_sqm))
        if cpi:
            hotel_cpi_medians.append(median(cpi))

    return {
        "observations": len(observations),
        "hotels": len(grouped),
        "average_adr_twd": round(mean(hotel_averages), 0) if hotel_averages else None,
        "median_adr_twd": round(median(hotel_medians), 0) if hotel_medians else None,
        "median_per_sqm_twd": round(median(hotel_per_sqm_medians), 0)
        if hotel_per_sqm_medians
        else None,
        "median_cpi_adjusted_twd": round(median(hotel_cpi_medians), 0)
        if hotel_cpi_medians
        else None,
    }

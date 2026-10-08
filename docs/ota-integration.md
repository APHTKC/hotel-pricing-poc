# OTA integration status

The dashboard stores OTA and official-site observations in the same rate schema,
while preserving `source_platform`, `source_method`, and `source_property_id`.
This makes source-to-source comparisons possible without mixing unlike prices.

## First provider: Booking.com Demand API

The first production-ready client uses Booking.com's official Demand API. It
requests one room for two adults in TWD and keeps the returned room product,
meal plan, cancellation policy, base price, and total price. The API credentials
are read only from environment variables and must never be committed.

Room sizes from the partner room-details response are accepted only when the
measurement unit is explicit. `SQM` is stored directly, while `SQFT` is converted
to square metres. Missing or unfamiliar units remain `null`, which keeps the
Canonical Comparison Key fail-closed instead of assigning an incorrect size band.

Required GitHub Actions secrets:

- `BOOKING_COM_API_KEY`
- `BOOKING_COM_AFFILIATE_ID`

Hotel mappings belong in `config/ota-properties.yaml` as internal Booking.com
accommodation IDs. Until both credentials and at least one mapping exist, the
OTA step exits successfully without making a network request. This prevents the
normal official-hotel collection from failing or consuming OTA quota.

Booking.com partner access is required before live use. After access is
approved, map one pilot hotel first, validate all six lead dates, and only then
add additional hotels in small batches.

### Find a property ID without scanning the full catalog

After the two credentials are present, resolve exactly one hotel at a time:

```powershell
.venv\Scripts\python.exe scripts\discover_booking_property.py capella_taipei
```

The command uses Booking.com's official `/common/autocomplete` endpoint with a
hotel-only filter. It prints ranked candidates and a mapping hint, but does not
modify configuration automatically. Review the name and city before copying the
chosen ID into `config/ota-properties.yaml`. This keeps API usage predictable
and avoids accidental bulk requests.

The scheduled collector also limits waste automatically: two consecutive empty
or failed responses stop the remaining dates for that hotel; HTTP 400/404/422
stops that property's remaining dates; and HTTP 401/403/429 stops the whole
provider run so invalid credentials or throttling are not retried across every
hotel.

## Deferred providers

- Agoda: official Online Affiliate/MSE credentials and certification required.
- Expedia/Hotels.com: Expedia Rapid partner access required.
- Rakuten Travel: retained for a future Japan market dataset; the current
  official Travel API is not a suitable primary source for Taiwan hotels.

## Visible-browser public snapshots

When partner credentials are not yet available, an operator may use a normal,
visible browser to capture a low-frequency public OTA offer. This is not a
CAPTCHA bypass and must stop at any login, verification, paywall, or access
barrier. Captures are stored separately in
`data/ota_browser_snapshots.jsonl` and are accepted by the static build only
when all Canonical Comparison Key fields are explicit: hotel, stay dates,
occupancy, room-size band, breakfast, cancellation class, and tax inclusion.

The latest public dashboard keeps the newest batch for each source platform.
Official rates alone feed the market ADR and heatmap; OTA snapshots may appear
in source-filtered details and strict rate-parity results. This prevents a
small asynchronous OTA capture from replacing or distorting the daily official
market batch.

The first verified browser pilot was Capella Taipei for 2026-11-06 to
2026-11-07 (one room, two adults), observed on 2026-10-08. Booking.com publicly
showed two complete products without login: a 48 sqm breakfast-inclusive,
free-cancellation room at TWD 30,800 including taxes and fees, and a 60 sqm
product under the same terms at TWD 42,300 including taxes and fees. These
records remain non-comparable until an official-site observation has the exact
same Canonical Comparison Key.

The second verified capture was W Taipei for 2026-11-13 to 2026-11-14. The
public room table exposed a 43 sqm Wonderful King room, the exact occupancy,
free-cancellation deadline, breakfast variants, and separate pre-tax and final
prices. The stored room-only total is TWD 15,015 and the breakfast-inclusive
total is TWD 16,632. Both totals include the separately displayed taxes and
other charges; the individual tax/service split remains null because the page
did not identify that split.

The third verified capture was Palais de Chine Hotel for 2026-10-15 to
2026-10-16. Booking.com exposed a 30 sqm Superior Double room for two adults,
without breakfast, with a dated free-cancellation deadline and a TWD 8,160
tax-and-fee-inclusive total. This product shares the official observation's
Canonical Comparison Key. Deadline-based free cancellation is normalized as
`conditional` regardless of whether a source places the date before or after
the words "free cancellation", preventing wording order from blocking a valid
same-product comparison.

Visible-browser checks that do not yield a complete bookable product are kept
in `data/ota_browser_checks.jsonl`. The log records the hotel, platform, stay,
status, and reason without publishing a price row. It prevents the next batch
from repeating the same hotel/date check after a legitimate no-availability or
access-barrier result.

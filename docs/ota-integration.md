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
`data/ota_browser_snapshots.jsonl`. A complete room offer must identify the
hotel, stay dates, occupancy, room, size band, meal plan, cancellation policy,
and displayed total. If the OTA page does not explicitly state whether that
total includes taxes, the observation may still appear in source-filtered
details with `tax_inclusion: unknown`, but it cannot form a Canonical
Comparison Key or enter strict parity results.

The latest public dashboard keeps the newest official batch and the newest OTA
batch for each platform and hotel. Official rates alone feed the market ADR and
heatmap; OTA snapshots may appear in source-filtered details and strict
rate-parity results. This prevents a small asynchronous OTA capture from
replacing or distorting the daily official market batch, while allowing
low-frequency OTA checks for different hotels to accumulate independently.
Strict parity results are calculated from the deduplicated history so they do
not disappear when the daily official lead dates roll forward. For each exact
Canonical Comparison Key, the newest OTA batch is paired only with the closest
official observation collected within 24 hours; older official observations
are rejected rather than mixed into a misleading median.

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

The fourth verified capture was Hotel Metropolitan Premier Taipei for
2026-10-15 to 2026-10-16. Booking.com exposed three room-only products for two
adults under the same dated free-cancellation and tax-inclusive terms: a 36 sqm
Standard Twin at TWD 6,696, a 43 sqm Superior King at TWD 7,254, and a 43 sqm
Superior Twin at TWD 7,254. These products share the official observations'
Canonical Comparison Key and therefore form a second strict rate-parity sample.

The fifth verified capture was The Okura Prestige Taipei for 2026-10-15 to
2026-10-16. Booking.com exposed a 44 sqm Deluxe Twin at TWD 10,349 under a
non-refundable room-only plan, TWD 10,350 under a full-cancellation-fee
room-only plan, and TWD 12,066 with breakfast under the same full-fee policy;
all totals include taxes and fees. The latest official batch exposed different
room-size bands and an unknown tax-inclusion field, so these snapshots are
published with complete Canonical Keys but correctly do not appear in strict
rate-parity results until an official observation has the exact same key.

The sixth verified capture was Mandarin Oriental, Taipei for 2026-10-19 to
2026-10-20. Booking.com publicly exposed seven two-adult products across 55 sqm
Deluxe King, Deluxe Twin, Executive Deluxe King and Club Deluxe Twin rooms, plus
a 70 sqm Mandarin Room. Displayed totals ranged from TWD 12,705 to TWD 22,176,
with explicit breakfast and dated free-cancellation terms. Because the page did
not explicitly label the displayed total as tax-inclusive or tax-exclusive,
these records use `tax_inclusion: unknown` and are deliberately excluded from
strict parity.

The seventh verified capture was Shangri-La Far Eastern, Taipei for 2026-10-19
to 2026-10-20. The normal public Booking.com room table exposed ten two-adult
products across 40 sqm Deluxe rooms, 60 sqm Premier and Horizon Club rooms, and
a 72 sqm Plaza Suite. Displayed totals ranged from TWD 11,781 to TWD 19,173,
with room-only and breakfast variants plus a dated free-cancellation deadline.
The page did not explicitly identify whether its displayed totals included or
excluded tax, so the snapshots remain visible source evidence with
`tax_inclusion: unknown` and cannot enter strict parity calculations.

The eighth verified capture was Grand HiLai Taipei for 2026-10-19 to
2026-10-20. Booking.com's normal public room table exposed room-only and
breakfast variants for 44 sqm Deluxe King and Deluxe Twin rooms at TWD 7,650
and TWD 8,925, plus a 59 sqm lounge-access Deluxe Suite with breakfast at
TWD 19,825. All five two-adult products displayed a dated free-cancellation
deadline and pay-at-property terms. The visible table did not explicitly state
whether totals included taxes, so the records use `tax_inclusion: unknown` and
remain outside strict parity calculations.

The ninth verified capture was Grand Mayfull Taipei for 2026-10-19 to
2026-10-20. Booking.com's public room table exposed twelve representative
two-adult products spanning 50, 60, 70, 95, and 105 sqm rooms and suites, with
room-only and breakfast variants. Displayed totals ranged from TWD 6,718 to
TWD 37,884 and included the visible promotional label plus a dated
free-cancellation deadline. Because the table did not explicitly state the tax
inclusion basis, these records use `tax_inclusion: unknown` and are excluded
from strict parity. A separate one-time check of Hotel Royal-Nikko Taipei for
the same stay explicitly returned no availability; that result is recorded in
`data/ota_browser_checks.jsonl` and was not retried in this batch.

The tenth verified capture was Grand Hyatt Taipei for 2026-10-19 to
2026-10-20. Booking.com's public room table exposed twenty-eight selected
two-adult products: room-only and breakfast-inclusive, free-cancellation
variants across fourteen rooms from 30 to 83 sqm, including city-view rooms,
Taipei 101-view rooms, lounge-access rooms, studios, and executive suites.
Displayed totals ranged from TWD 16,055 to TWD 29,915. Single-occupancy and
non-refundable variants were deliberately omitted from this capture so the
published set retains a consistent occupancy and cancellation class. Because
the visible table did not explicitly label its tax-inclusion basis, all records
use `tax_inclusion: unknown` and remain outside strict parity calculations.

The eleventh verified capture was Sheraton Grand Taipei Hotel for 2026-10-19
to 2026-10-20. Booking.com's public room table exposed six two-adult products:
room-only and breakfast-inclusive, free-cancellation variants for a 40 sqm
Premier Twin and 35 sqm Executive Deluxe King and Twin rooms. Displayed totals
ranged from TWD 10,280 to TWD 12,821, with a common dated cancellation deadline
and pay-at-property terms. The page did not explicitly label the displayed
total's tax-inclusion basis, so these records use `tax_inclusion: unknown` and
remain outside strict parity calculations.

The next low-cost availability batch checked Le Meridien Taipei and Taipei
Marriott Hotel for 2026-10-19 to 2026-10-20. Booking.com's public property
pages explicitly reported no availability for both hotels. No rate rows were
published and no alternate dates were retried in the same batch. These are
dated availability observations rather than permanent source failures.

A subsequent one-check batch searched Courtyard by Marriott Taipei for
2026-11-11 to 2026-11-12. Booking.com's own search resolved the canonical
property page but explicitly marked the selected stay unavailable. The result
was recorded without publishing a price row or trying alternate dates.

The following one-check batch searched Courtyard by Marriott Taipei Downtown
for the same 2026-11-11 to 2026-11-12 stay. Booking.com's canonical property
result likewise reported no availability. No price was inferred or published,
and the batch did not retry another date.

Hotel Proverbs Taipei was then checked once for 2026-11-11 to 2026-11-12.
Booking.com's own search resolved the canonical property page but explicitly
reported no availability. The batch published no price row and did not retry
another date.

Renaissance Taipei Shihlin Hotel was checked once for 2026-11-12 to
2026-11-13. Booking.com's canonical result explicitly marked the selected stay
unavailable, so the batch recorded the observation without publishing a price
or trying another date.

Humble House Taipei, Curio Collection by Hilton was checked once for
2026-11-13 to 2026-11-14. Booking.com's site search resolved the canonical
property page but explicitly reported no availability for the selected stay.
The batch published no price row and did not retry another date.

Kimpton Da An was checked once for 2026-11-15 to 2026-11-16. Booking.com's
canonical property result explicitly reported no availability for the selected
stay, so the batch kept a dated diagnostic only and did not retry another date.

Hotel Indigo Taipei North was checked once for 2026-11-16 to 2026-11-17.
Booking.com's site search resolved the canonical property page but explicitly
reported no availability for the selected stay. The batch published no price
row and did not retry another date.

Visible-browser checks that do not yield a complete bookable product are kept
in `data/ota_browser_checks.jsonl`. The log records the hotel, platform, stay,
status, and reason without publishing a price row. It prevents the next batch
from repeating the same hotel/date check after a legitimate no-availability or
access-barrier result.

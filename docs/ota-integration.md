# OTA integration status

The dashboard stores OTA and official-site observations in the same rate schema,
while preserving `source_platform`, `source_method`, and `source_property_id`.
This makes source-to-source comparisons possible without mixing unlike prices.

## First provider: Booking.com Demand API

The first production-ready client uses Booking.com's official Demand API. It
requests one room for two adults in TWD and keeps the returned room product,
meal plan, cancellation policy, base price, and total price. The API credentials
are read only from environment variables and must never be committed.

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

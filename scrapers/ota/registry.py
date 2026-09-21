from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class OtaProviderSpec:
    platform: str
    display_name: str
    required_environment: tuple[str, ...]

    def is_configured(self, environment: Mapping[str, str]) -> bool:
        return all(environment.get(name, "").strip() for name in self.required_environment)


OTA_PROVIDER_SPECS = (
    OtaProviderSpec(
        "booking_com",
        "Booking.com",
        ("BOOKING_COM_API_KEY", "BOOKING_COM_AFFILIATE_ID"),
    ),
    OtaProviderSpec("agoda", "Agoda", ("AGODA_API_KEY", "AGODA_SITE_ID")),
    OtaProviderSpec(
        "expedia_group",
        "Hotels.com / Expedia",
        ("EXPEDIA_RAPID_API_KEY", "EXPEDIA_RAPID_SHARED_SECRET"),
    ),
    OtaProviderSpec(
        "rakuten_travel",
        "Rakuten Travel",
        ("RAKUTEN_APP_ID", "RAKUTEN_ACCESS_KEY"),
    ),
)


def configured_ota_providers(environment: Mapping[str, str]) -> list[OtaProviderSpec]:
    """List providers whose complete credential set is available."""
    return [spec for spec in OTA_PROVIDER_SPECS if spec.is_configured(environment)]

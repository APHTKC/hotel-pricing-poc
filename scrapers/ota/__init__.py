"""Authorized OTA rate-provider interfaces.

Providers in this package are enabled only after partner credentials and hotel
property mappings have been supplied. They do not scrape consumer web pages.
"""

from .base import OtaRateProvider
from .registry import OTA_PROVIDER_SPECS, OtaProviderSpec, configured_ota_providers

__all__ = ["OTA_PROVIDER_SPECS", "OtaProviderSpec", "OtaRateProvider", "configured_ota_providers"]

from app.settings import Settings
from scrapers.adapters.capella import CapellaScraper
from scrapers.adapters.ihg import IHGScraper
from scrapers.adapters.mandarin_oriental import MandarinOrientalScraper
from scrapers.adapters.marriott import MarriottScraper
from scrapers.adapters.okura import OkuraScraper
from scrapers.adapters.shangrila import ShangriLaScraper
from scrapers.base import HotelScraper
from scrapers.demo import DemoScraper


ADAPTERS: dict[str, type[HotelScraper]] = {
    "mandarin_oriental": MandarinOrientalScraper,
    "ihg": IHGScraper,
    "marriott": MarriottScraper,
    "okura": OkuraScraper,
    "shangrila": ShangriLaScraper,
    "capella": CapellaScraper,
}


def get_scraper(adapter_name: str, settings: Settings) -> HotelScraper:
    if settings.demo_mode:
        return DemoScraper()
    if adapter_name not in ADAPTERS:
        raise KeyError(f"Unknown adapter: {adapter_name}")
    return ADAPTERS[adapter_name]()

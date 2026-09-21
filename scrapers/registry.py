from app.settings import Settings
from scrapers.adapters.capella import CapellaScraper
from scrapers.adapters.grand_hilai import GrandHiLaiScraper
from scrapers.adapters.grand_mayfull import GrandMayfullScraper
from scrapers.adapters.grand_view import GrandViewScraper
from scrapers.adapters.gobooking import GobookingScraper
from scrapers.adapters.ihg import IHGScraper
from scrapers.adapters.hoshinoya import HoshinoyaScraper
from scrapers.adapters.mandarin_oriental import MandarinOrientalScraper
from scrapers.adapters.marriott import MarriottScraper
from scrapers.adapters.okura import OkuraScraper
from scrapers.adapters.royal_nikko import RoyalNikkoScraper
from scrapers.adapters.shangrila import ShangriLaScraper
from scrapers.adapters.siteminder import SiteMinderScraper
from scrapers.adapters.synxis import SynxisScraper
from scrapers.adapters.tripla import TriplaScraper
from scrapers.base import HotelScraper
from scrapers.demo import DemoScraper


ADAPTERS: dict[str, type[HotelScraper]] = {
    "mandarin_oriental": MandarinOrientalScraper,
    "ihg": IHGScraper,
    "hoshinoya": HoshinoyaScraper,
    "marriott": MarriottScraper,
    "okura": OkuraScraper,
    "shangrila": ShangriLaScraper,
    "siteminder": SiteMinderScraper,
    "capella": CapellaScraper,
    "grand_hilai": GrandHiLaiScraper,
    "grand_mayfull": GrandMayfullScraper,
    "grand_view": GrandViewScraper,
    "gobooking": GobookingScraper,
    "royal_nikko": RoyalNikkoScraper,
    "synxis": SynxisScraper,
    "tripla": TriplaScraper,
}


def get_scraper(adapter_name: str, settings: Settings) -> HotelScraper:
    if settings.demo_mode:
        return DemoScraper()
    if adapter_name not in ADAPTERS:
        raise KeyError(f"Unknown adapter: {adapter_name}")
    return ADAPTERS[adapter_name]()

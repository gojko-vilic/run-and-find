from urllib.parse import urlparse

from .amazon import AmazonScraper
from .amazon import DOMAINS as AMAZON_DOMAINS
from .austrian import AustrianScraper
from .austrian import DOMAINS as AUSTRIAN_DOMAINS
from .base import BaseScraper
from .serbian import SerbianScraper
from .serbian import DOMAINS as SERBIAN_DOMAINS
from .trebapatike import TrebaPatikeScraper
from .trebapatike import DOMAINS as TREBAPATIKE_DOMAINS


def get_scraper(url: str) -> BaseScraper:
    """Return the appropriate scraper for the given URL."""
    host = urlparse(url).hostname or ""
    clean = host.removeprefix("www.")

    def matches(domains: list[str]) -> bool:
        return any(clean == d or clean.endswith("." + d) for d in domains)

    if matches(TREBAPATIKE_DOMAINS):
        return TrebaPatikeScraper()
    if matches(AMAZON_DOMAINS):
        return AmazonScraper()
    if matches(AUSTRIAN_DOMAINS):
        return AustrianScraper()
    if matches(SERBIAN_DOMAINS):
        return SerbianScraper()
    # Generic fallback: tries JSON-LD and microdata
    return BaseScraper()

from urllib.parse import urlparse
import random
import time

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, ScrapingError, HEADERS

DOMAINS = [
    "amazon.com",
    "amazon.de",
    "amazon.co.uk",
    "amazon.at",
    "amazon.fr",
    "amazon.es",
    "amazon.it",
    "amazon.nl",
]

_TLD_CURRENCY = {
    "amazon.com": "USD",
    "amazon.de": "EUR",
    "amazon.at": "EUR",
    "amazon.fr": "EUR",
    "amazon.es": "EUR",
    "amazon.it": "EUR",
    "amazon.nl": "EUR",
    "amazon.co.uk": "GBP",
}

# Tried in order; first match wins
_PRICE_SELECTORS = [
    ".priceToPay",  # primary — JS-free current price
    "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
    "#apex_desktop .a-price .a-offscreen",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "#item_price",  # marketplace seller template
]


class AmazonScraper(BaseScraper):
    # Delay range in seconds between requests to avoid bot detection
    _DELAY = (3.0, 7.0)

    # Language header keyed by TLD
    _ACCEPT_LANG = {
        "amazon.de": "de-DE,de;q=0.9,en;q=0.8",
        "amazon.at": "de-AT,de;q=0.9,en;q=0.8",
        "amazon.fr": "fr-FR,fr;q=0.9,en;q=0.8",
        "amazon.es": "es-ES,es;q=0.9,en;q=0.8",
        "amazon.it": "it-IT,it;q=0.9,en;q=0.8",
        "amazon.nl": "nl-NL,nl;q=0.9,en;q=0.8",
        "amazon.co.uk": "en-GB,en;q=0.9",
        "amazon.com": "en-US,en;q=0.9",
    }

    def fetch(self, url: str) -> BeautifulSoup:
        time.sleep(random.uniform(*self._DELAY))
        hostname = urlparse(url).hostname or ""
        clean = hostname.removeprefix("www.")
        headers = {
            **HEADERS,
            "Accept-Language": self._ACCEPT_LANG.get(clean, "en-US,en;q=0.9"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    def scrape(self, url: str) -> dict:
        soup = self.fetch(url)

        hostname = urlparse(url).hostname or ""
        clean = hostname.removeprefix("www.")
        currency = _TLD_CURRENCY.get(clean, "EUR")

        name_tag = soup.select_one("#productTitle")
        name = name_tag.get_text(strip=True) if name_tag else ""

        for selector in _PRICE_SELECTORS:
            tag = soup.select_one(selector)
            if tag:
                try:
                    return {
                        "name": name,
                        "price": self.parse_price(tag.get_text()),
                        "currency": currency,
                    }
                except ValueError:
                    continue

        # JSON-LD fallback (Amazon embeds it on some pages)
        result = self._from_jsonld(soup)
        if result:
            result["name"] = result["name"] or name
            result.setdefault("currency", currency)
            return result

        raise ScrapingError(f"Could not extract Amazon price from {url}")

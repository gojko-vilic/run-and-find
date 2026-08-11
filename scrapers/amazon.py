from urllib.parse import urlparse

from .base import BaseScraper, ScrapingError

DOMAINS = [
    "amazon.com", "amazon.de", "amazon.co.uk", "amazon.at",
    "amazon.fr", "amazon.es", "amazon.it", "amazon.nl",
]

_TLD_CURRENCY = {
    "amazon.com":   "USD",
    "amazon.de":    "EUR",
    "amazon.at":    "EUR",
    "amazon.fr":    "EUR",
    "amazon.es":    "EUR",
    "amazon.it":    "EUR",
    "amazon.nl":    "EUR",
    "amazon.co.uk": "GBP",
}

# Tried in order; first match wins
_PRICE_SELECTORS = [
    "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
    "#apex_desktop .a-price .a-offscreen",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    ".a-price .a-offscreen",
]


class AmazonScraper(BaseScraper):
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
                    return {"name": name, "price": self.parse_price(tag.get_text()), "currency": currency}
                except ValueError:
                    continue

        # JSON-LD fallback (Amazon embeds it on some pages)
        result = self._from_jsonld(soup)
        if result:
            result["name"] = result["name"] or name
            result.setdefault("currency", currency)
            return result

        raise ScrapingError(f"Could not extract Amazon price from {url}")

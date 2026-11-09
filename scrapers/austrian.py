from .base import BaseScraper, ScrapingError

# Verified running shoe retailers in Austria (confirmed live stores)
DOMAINS = [
    "intersport.at",  # Intersport Austria
    "sport-eybl.at",  # Sport Eybl (Austrian sports chain)
    "decathlon.at",  # Decathlon Austria
    "hervis.at",  # Hervis Sport (confirmed: has Running Welt section)
    "sportler.com",  # Sportler — South Tyrol/AT running specialist
    "aboutyou.at",  # About You AT
]

_SITE_SELECTORS: dict[str, tuple[str, str]] = {
    "intersport.at": (".price, .product-price, [class*='price']", "EUR"),
    "sport-eybl.at": (".price, .product-price, [class*='price']", "EUR"),
    "decathlon.at": (".price, [itemprop='price']", "EUR"),
    "hervis.at": (".price, .product-price, [class*='price']", "EUR"),
    "sportler.com": (".price, .product-price, [class*='price']", "EUR"),
    "aboutyou.at": ("[data-testid='price'], [class*='price']", "EUR"),
}


class AustrianScraper(BaseScraper):
    def scrape(self, url: str) -> dict:
        soup = self.fetch(url)

        result = self._from_jsonld(soup) or self._from_microdata(soup)
        if result:
            result.setdefault("currency", "EUR")
            return result

        host = url.split("/")[2].removeprefix("www.")
        for domain, (selector, currency) in _SITE_SELECTORS.items():
            if domain not in host:
                continue
            tag = soup.select_one(selector)
            if tag:
                name_tag = soup.find("h1")
                return {
                    "name": name_tag.get_text(strip=True) if name_tag else "",
                    "price": self.parse_price(tag.get_text()),
                    "currency": currency,
                }

        raise ScrapingError(f"Could not extract price from {url}")

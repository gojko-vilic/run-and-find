from .base import BaseScraper, ScrapingError

# Verified running shoe retailers in Serbia (confirmed live stores, not domain-for-sale pages)
DOMAINS = [
    "sport-vision.rs",  # Sport Vision — major ex-YU sports chain
    "intersport.rs",  # Intersport Serbia
    "decathlon.rs",  # Decathlon Serbia
    "ananas.rs",  # Ananas marketplace (RS Amazon equivalent)
    "mall.rs",  # Mall.rs marketplace
    "aboutyou.rs",  # About You fashion + shoes
    "buzzsneakers.rs",  # Buzz Sneakers
    "tike.rs",  # Tike.rs shoe store
    "runandmore.rs",  # Run and More — running specialist (403 on bots, try with stealth headers)
    "runnmore.com",  # Run'n More — Serbian running specialist (Belgrade)
]

# CSS selector → default currency for each supported domain
_SITE_SELECTORS: dict[str, tuple[str, str]] = {
    "sport-vision.rs": (".price, .product-price, [class*='price']", "RSD"),
    "intersport.rs": (".price, .product-price, [class*='price']", "RSD"),
    "decathlon.rs": (".price, [itemprop='price']", "RSD"),
    "ananas.rs": ("[data-testid='product-price'], [class*='price']", "RSD"),
    "mall.rs": (".price, .product-price, [class*='price']", "RSD"),
    "aboutyou.rs": ("[data-testid='price'], [class*='price']", "RSD"),
    "buzzsneakers.rs": (".price, .product-price, [class*='price']", "RSD"),
    "tike.rs": (".price, .product-price, [class*='price']", "RSD"),
    "runandmore.rs": (".price, .product-price, [class*='price']", "RSD"),
    "runnmore.com": (".price, .product-price, [class*='price']", "RSD"),
}


class SerbianScraper(BaseScraper):
    def scrape(self, url: str) -> dict:
        soup = self.fetch(url)

        result = self._from_jsonld(soup) or self._from_microdata(soup)
        if result:
            result.setdefault("currency", "RSD")
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

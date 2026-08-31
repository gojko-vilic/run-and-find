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
    @staticmethod
    def _spec_gender(soup) -> str | None:
        """Gender from the "Pol" specification row, if the page has one.

        This is the retailer's own product attribute, so it is trusted over the
        marketing description — the two genuinely disagree on some listings.
        """
        for item in soup.select(".nb-items-wrapper .nb-item"):
            cells = [
                c.get_text(" ", strip=True)
                for c in item.find_all(["p", "a"], recursive=False)
            ]
            if len(cells) >= 2 and cells[0] == "Pol":
                return BaseScraper.detect_gender(cells[1])
        return None

    def scrape(self, url: str) -> dict:
        soup = self.fetch(url)

        # Product pages for men's and women's colourways often share a name, so
        # gender has to come from the page, not the title.
        heading = soup.find("h1")
        gender = self._spec_gender(soup) or self.detect_gender(
            heading.get_text(" ", strip=True) if heading else ""
        )

        result = self._from_jsonld(soup) or self._from_microdata(soup)
        if result:
            result.setdefault("currency", "RSD")
            result["gender"] = gender
            return result

        host = url.split("/")[2].removeprefix("www.")
        for domain, (selector, currency) in _SITE_SELECTORS.items():
            if domain not in host:
                continue
            tag = soup.select_one(selector)
            if tag:
                return {
                    "name": heading.get_text(strip=True) if heading else "",
                    "price": self.parse_price(tag.get_text()),
                    "currency": currency,
                    "gender": gender,
                }

        raise ScrapingError(f"Could not extract price from {url}")

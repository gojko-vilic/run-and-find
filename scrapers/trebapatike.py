import json

from .base import BaseScraper, ScrapingError

DOMAINS = ["trebapatike.rs"]


class TrebaPatikeScraper(BaseScraper):
    """Scrapes all per-store offers from trebapatike.rs JSON-LD."""

    def scrape(self, url: str) -> dict:
        offers = self.scrape_offers(url)
        lowest = min(offers, key=lambda o: o["price"])
        return {
            "name": lowest["name"],
            "price": lowest["price"],
            "currency": lowest["currency"],
        }

    def scrape_offers(self, url: str) -> list[dict]:
        soup = self.fetch(url)
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string)
            except (json.JSONDecodeError, TypeError):
                continue
            graph = data.get("@graph", [data])
            for node in graph:
                if node.get("@type") != "Product":
                    continue
                agg = node.get("offers", {})
                name = node.get("name", "")
                default_currency = agg.get("priceCurrency", "RSD")
                raw = agg.get("offers", [])
                if isinstance(raw, dict):
                    raw = [raw]
                offers = []
                for o in raw:
                    seller = o.get("seller", {})
                    offers.append(
                        {
                            "name": name,
                            "store": seller.get("name", "Unknown"),
                            "sku": o.get("sku", ""),
                            "price": float(o["price"]),
                            "currency": o.get("priceCurrency", default_currency),
                            "store_url": o.get("url", url),
                        }
                    )
                if offers:
                    return offers
        raise ScrapingError(f"No JSON-LD offers found at {url}")

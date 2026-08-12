import json
import re
from collections import defaultdict, deque

from .base import BaseScraper, ScrapingError

DOMAINS = ["trebapatike.rs"]


class TrebaPatikeScraper(BaseScraper):
    """Scrapes all per-store offers from trebapatike.rs JSON-LD."""

    def scrape(self, url: str) -> dict:
        offers = self.scrape_offers(url)
        in_stock = [o for o in offers if o["in_stock"]]
        if not in_stock:
            raise ScrapingError(f"No in-stock offers at {url}")
        lowest = min(in_stock, key=lambda o: o["price"])
        return {
            "name": lowest["name"],
            "price": lowest["price"],
            "currency": lowest["currency"],
        }

    @staticmethod
    def _gender_map(soup) -> dict:
        """Returns {(store, price): deque([gender, ...])} from HTML offer cards."""
        result: dict = defaultdict(deque)
        for a in soup.find_all("a", href=lambda h: h and h.startswith("/go/")):
            parts = [
                p.strip() for p in re.split(r"[|\n]", a.get_text("|")) if p.strip()
            ]
            if len(parts) < 4:
                continue
            store = parts[0]
            label = parts[1]  # e.g. "Muški, Crvena" or "Ženski, Bordo"
            # Price is a run of digits separated by narrow/non-breaking spaces
            price = None
            for p in parts[2:]:
                cleaned = re.sub(r"[\s\u00a0\u202f\u2009]+", "", p)
                try:
                    val = float(cleaned)
                    if val > 100:  # skip size counts and discount %
                        price = val
                        break
                except ValueError:
                    continue
            if price is None:
                continue
            if "Muški" in label:
                gender = "men"
            elif "Ženski" in label:
                gender = "women"
            else:
                gender = "unisex"
            result[(store, price)].append(gender)
        return result

    def scrape_offers(self, url: str) -> list[dict]:
        soup = self.fetch(url)
        gender_map = self._gender_map(soup)
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
                    availability = o.get("availability", "")
                    store = seller.get("name", "Unknown")
                    price = float(o["price"])
                    key = (store, price)
                    # popleft preserves HTML order for same-store same-price collisions
                    gender = (
                        gender_map[key].popleft() if gender_map.get(key) else "unisex"
                    )
                    offers.append(
                        {
                            "name": name,
                            "store": store,
                            "sku": o.get("sku", ""),
                            "price": price,
                            "currency": o.get("priceCurrency", default_currency),
                            "store_url": o.get("url", url),
                            "in_stock": not availability
                            or availability.endswith("InStock"),
                            "gender": gender,
                        }
                    )
                if offers:
                    return offers
        raise ScrapingError(f"No JSON-LD offers found at {url}")

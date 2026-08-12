import json
import re

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xhtml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class ScrapingError(Exception):
    pass


class BaseScraper:
    def fetch(self, url: str) -> BeautifulSoup:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    def scrape(self, url: str) -> dict:
        """Returns {'name': str, 'price': float, 'currency': str}."""
        soup = self.fetch(url)
        result = self._from_jsonld(soup) or self._from_microdata(soup)
        if not result:
            raise ScrapingError(f"Could not extract price from {url}")
        return result

    @staticmethod
    def parse_price(text: str) -> float:
        cleaned = re.sub(r"[^\d,.]", "", text.strip())
        if "," in cleaned and "." in cleaned:
            # European thousands format: 1.234,56 → 1234.56
            if cleaned.index(".") < cleaned.index(","):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        return float(cleaned)

    @staticmethod
    def _from_jsonld(soup: BeautifulSoup) -> dict | None:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    data = data[0]
                if data.get("@type") not in ("Product", "ProductGroup"):
                    continue
                name = data.get("name", "")
                offer = data.get("offers", {})
                if isinstance(offer, list):
                    offer = offer[0]
                price = float(offer.get("price") or 0)
                currency = offer.get("priceCurrency", "")
                availability = offer.get("availability", "")
                in_stock = not availability or availability.endswith("InStock")
                if price:
                    return {
                        "name": name,
                        "price": price,
                        "currency": currency,
                        "in_stock": in_stock,
                    }
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                continue
        return None

    @staticmethod
    def _from_microdata(soup: BeautifulSoup) -> dict | None:
        tag = soup.find(itemprop="price")
        if not tag:
            return None
        try:
            raw = tag.get("content") or tag.get_text()
            price = BaseScraper.parse_price(raw)
            name_tag = soup.find(itemprop="name")
            name = name_tag.get_text(strip=True) if name_tag else ""
            cur_tag = soup.find(itemprop="priceCurrency")
            currency = (cur_tag.get("content") or "") if cur_tag else ""
            return {"name": name, "price": price, "currency": currency}
        except (ValueError, AttributeError):
            return None

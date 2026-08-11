import json
import os
import sys
from pathlib import Path

import requests
import yaml

from scrapers import get_scraper
from scrapers.base import ScrapingError

PRODUCTS_FILE = Path("products.yaml")
PRICES_FILE = Path("data/last_prices.json")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")


def send_telegram(message: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        print(f"[TELEGRAM - no token set]\n{message}")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"},
        timeout=10,
    )


def load_products() -> list[dict]:
    return yaml.safe_load(PRODUCTS_FILE.read_text(encoding="utf-8"))["products"]


def load_prices() -> dict:
    if PRICES_FILE.exists():
        return json.loads(PRICES_FILE.read_text(encoding="utf-8"))
    return {}


def save_prices(prices: dict) -> None:
    PRICES_FILE.parent.mkdir(exist_ok=True)
    PRICES_FILE.write_text(
        json.dumps(prices, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main() -> None:
    products = load_products()
    prices = load_prices()
    errors: list[str] = []

    for product in products:
        url = product["url"]
        label = product.get("name") or url

        try:
            result = get_scraper(url).scrape(url)
        except (ScrapingError, Exception) as exc:
            msg = f"⚠️ {label}: {exc}"
            errors.append(msg)
            print(msg, file=sys.stderr)
            continue

        current = result["price"]
        currency = result["currency"]
        last = prices.get(url, {})
        last_price = last.get("price")

        if last_price is not None and current < last_price:
            diff = last_price - current
            send_telegram(
                f"🔔 <b>Price drop!</b>\n"
                f"<b>{label}</b>\n"
                f"{last_price:.2f} → <b>{current:.2f} {currency}</b> "
                f"(−{diff:.2f} {currency})\n"
                f'<a href="{url}">View product</a>'
            )

        prices[url] = {
            "price": current,
            "currency": currency,
            "name": result.get("name") or label,
        }

    save_prices(prices)

    if errors:
        send_telegram("⚠️ <b>Scraping errors</b>\n" + "\n".join(errors))


if __name__ == "__main__":
    main()

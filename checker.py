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


def _process_single(url: str, label: str, scraper, prices: dict, errors: list) -> None:
    try:
        result = scraper.scrape(url)
    except (ScrapingError, Exception) as exc:
        msg = f"⚠️ {label}: {exc}"
        errors.append(msg)
        print(msg, file=sys.stderr)
        return

    current = result["price"]
    currency = result["currency"]
    in_stock = result.get("in_stock", True)
    stored = prices.get(url, {})
    last_price = stored.get("price")
    was_in_stock = stored.get("in_stock", True)

    if in_stock and not was_in_stock:
        send_telegram(
            f"✅ <b>Back in stock!</b>\n"
            f"<b>{label}</b>\n"
            f'<a href="{url}">View product</a>'
        )

    if in_stock and last_price is not None and current < last_price:
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
        "in_stock": in_stock,
    }


def _process_multi_offer(
    url: str,
    label: str,
    scraper,
    prices: dict,
    errors: list,
    gender_filter: list[str] | None = None,
) -> None:
    try:
        offers = scraper.scrape_offers(url)
    except (ScrapingError, Exception) as exc:
        msg = f"⚠️ {label}: {exc}"
        errors.append(msg)
        print(msg, file=sys.stderr)
        return

    stored = prices.setdefault(url, {"name": label, "offers": {}})
    stored_offers: dict = stored.setdefault("offers", {})

    for offer in offers:
        if gender_filter and offer.get("gender", "unisex") not in gender_filter:
            continue
        key = f"{offer['store']}|{offer['sku']}"
        current = offer["price"]
        currency = offer["currency"]
        in_stock = offer.get("in_stock", True)
        store_url = offer["store_url"]
        store_name = offer["store"]
        prev = stored_offers.get(key, {})
        last_price = prev.get("price")
        was_in_stock = prev.get("in_stock", True)

        if in_stock and not was_in_stock:
            send_telegram(
                f"✅ <b>Back in stock!</b>\n"
                f"<b>{label}</b> @ <b>{store_name}</b>\n"
                f'<a href="{store_url}">View at {store_name}</a>'
            )

        if in_stock and last_price is not None and current < last_price:
            diff = last_price - current
            send_telegram(
                f"🔔 <b>Price drop!</b>\n"
                f"<b>{label}</b> @ <b>{store_name}</b>\n"
                f"{last_price:.0f} → <b>{current:.0f} {currency}</b> "
                f"(−{diff:.0f} {currency})\n"
                f'<a href="{store_url}">View at {store_name}</a>'
            )

        stored_offers[key] = {
            "price": current,
            "currency": currency,
            "store_url": store_url,
            "in_stock": in_stock,
        }

    stored["name"] = offers[0]["name"] if offers else label


def main() -> None:
    products = load_products()
    prices = load_prices()
    errors: list[str] = []

    for product in products:
        url = product["url"]
        label = product.get("name") or url
        scraper = get_scraper(url)

        try:
            if hasattr(scraper, "scrape_offers"):
                gender_raw = product.get("gender")
                gender_filter = (
                    [gender_raw]
                    if isinstance(gender_raw, str)
                    else list(gender_raw) if gender_raw else None
                )
                _process_multi_offer(url, label, scraper, prices, errors, gender_filter)
            else:
                _process_single(url, label, scraper, prices, errors)
        except Exception as exc:
            msg = f"⚠️ {label}: {exc}"
            errors.append(msg)
            print(msg, file=sys.stderr)

    save_prices(prices)

    if errors:
        send_telegram("⚠️ <b>Scraping errors</b>\n" + "\n".join(errors))


if __name__ == "__main__":
    main()

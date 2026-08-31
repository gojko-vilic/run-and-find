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


def _process_single(
    url: str,
    label: str,
    scraper,
    prices: dict,
    errors: list,
    gender_filter: list[str] | None = None,
) -> None:
    try:
        result = scraper.scrape(url)
    except (ScrapingError, Exception) as exc:
        msg = f"⚠️ {label}: {exc}"
        errors.append(msg)
        print(msg, file=sys.stderr)
        return

    # A single-product url has one gender, so a mismatch means the url itself
    # points at the wrong model — report it rather than tracking it silently.
    gender = result.get("gender", "unisex")
    if gender_filter and gender not in gender_filter:
        msg = (
            f"⚠️ {label}: url is the {gender}'s model, "
            f"wanted {'/'.join(gender_filter)} — not tracked"
        )
        errors.append(msg)
        print(msg, file=sys.stderr)
        prices.pop(url, None)
        return

    current = result["price"]
    currency = result["currency"]
    in_stock = result.get("in_stock", True)
    is_new = url not in prices
    stored = prices.get(url, {})
    last_price = stored.get("price")
    was_in_stock = stored.get("in_stock", True)

    # An unavailable product has no price to read. Keep the last known one so a
    # later drop is still measured against a real number rather than nothing.
    if current is None:
        current = last_price
        in_stock = False
        currency = currency or stored.get("currency", "")

    # First time we can put a number on this shoe — either it was just added to
    # products.yaml, or it was tracked with no price. Report it so a new entry
    # confirms itself instead of staying silent until it happens to drop. It
    # already says the shoe is available, so the restock notice would be noise.
    if in_stock and current is not None and (is_new or last_price is None):
        send_telegram(
            f"💰 <b>Current price</b>\n"
            f"<b>{label}</b>\n"
            f"<b>{current:.2f} {currency}</b>\n"
            f'<a href="{url}">View product</a>'
        )
    elif in_stock and not was_in_stock:
        send_telegram(
            f"✅ <b>Back in stock!</b>\n"
            f"<b>{label}</b>\n"
            f'<a href="{url}">View product</a>'
        )

    if (
        in_stock
        and current is not None
        and last_price is not None
        and current < last_price
    ):
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

    is_new = url not in prices
    stored = prices.setdefault(url, {"name": label, "offers": {}})
    stored_offers: dict = stored.setdefault("offers", {})
    # Whether we already knew a price for this shoe at any store, and the best
    # of those — the bar a newly appearing store has to beat.
    known_prices = [
        o["price"] for o in stored_offers.values() if o.get("price") is not None
    ]
    had_price = bool(known_prices)
    best_known = min(known_prices, default=None)

    if not offers:
        # Listing exists but no store carries it — retire what we knew so the
        # restock notification still fires when it comes back.
        for prev in stored_offers.values():
            prev["in_stock"] = False
        return

    tracked: list[dict] = []
    newcomers: list[dict] = []

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

        if in_stock:
            tracked.append(offer)
            # A store never seen for this shoe has no price history of its own,
            # so the drop check below can never flag it however cheap it is.
            if key not in stored_offers:
                newcomers.append(offer)

        # Suppressed on a shoe's first priced run: the "current price" notice
        # below already reports it, per shoe rather than once per store.
        if in_stock and not was_in_stock and had_price:
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

    # First time we can put a number on this shoe. One message for the whole
    # shoe quoting its cheapest store, not one per store.
    if (is_new or not had_price) and tracked:
        best = min(tracked, key=lambda o: o["price"])
        send_telegram(
            f"💰 <b>Current price</b>\n"
            f"<b>{label}</b> @ <b>{best['store']}</b>\n"
            f"<b>{best['price']:.0f} {best['currency']}</b>\n"
            f'<a href="{best["store_url"]}">View at {best["store"]}</a>'
        )

    # A store arriving below everything we knew is the actionable newcomer: its
    # own history is empty, so the per-offer drop check cannot catch it.
    undercuts = [
        o for o in newcomers if best_known is not None and o["price"] < best_known
    ]
    if had_price and undercuts:
        best = min(undercuts, key=lambda o: o["price"])
        send_telegram(
            f"🆕 <b>New cheapest store</b>\n"
            f"<b>{label}</b> @ <b>{best['store']}</b>\n"
            f"<b>{best['price']:.0f} {best['currency']}</b> "
            f"(best was {best_known:.0f} {best['currency']})\n"
            f'<a href="{best["store_url"]}">View at {best["store"]}</a>'
        )

    stored["name"] = offers[0]["name"] if offers else label


def main() -> None:
    products = load_products()
    prices = load_prices()
    errors: list[str] = []

    for product in products:
        url = product["url"]
        label = product.get("name") or url
        scraper = get_scraper(url)

        gender_raw = product.get("gender")
        gender_filter = (
            [gender_raw]
            if isinstance(gender_raw, str)
            else list(gender_raw) if gender_raw else None
        )

        try:
            if hasattr(scraper, "scrape_offers"):
                _process_multi_offer(url, label, scraper, prices, errors, gender_filter)
            else:
                _process_single(url, label, scraper, prices, errors, gender_filter)
        except Exception as exc:
            msg = f"⚠️ {label}: {exc}"
            errors.append(msg)
            print(msg, file=sys.stderr)

    save_prices(prices)

    if errors:
        send_telegram("⚠️ <b>Scraping errors</b>\n" + "\n".join(errors))


if __name__ == "__main__":
    main()

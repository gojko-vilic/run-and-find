from urllib.parse import urljoin, urlparse
import json
import os
import random
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, ScrapingError
from .sizes import parse_amazon_size

DOMAINS = [
    "amazon.com",
    "amazon.de",
    "amazon.co.uk",
    "amazon.at",
    "amazon.fr",
    "amazon.es",
    "amazon.it",
    "amazon.nl",
]

# Price and availability depend on where Amazon thinks the order ships to, and
# a fresh session is placed by IP: a GitHub runner in the US, or wherever the
# script happens to run. The orders go to Austria, so every session is pointed
# there before a price is read — an item Amazon will not deliver to Austria is
# not a price for us, however cheap it is elsewhere.
SHIP_TO_COUNTRY = os.environ.get("AMAZON_SHIP_TO", "AT")

# The location picker ("glow") endpoints, relative to the store root
_GLOW_CHANGE_PATH = "/portal-migration/hz/glow/address-change"

# Amazon still quotes a price for an item it refuses to deliver to the chosen
# country; the refusal is only in the delivery block. Per storefront language.
_UNDELIVERABLE = re.compile(
    r"kann nicht an (?:den|die) von dir ausgewählten (?:Lieferort|Zustellungsort)"
    r"|cannot be shipped to your selected delivery location"
    r"|ne peut pas être expédié à l'adresse"
    r"|non può essere spedito presso l'indirizzo"
    r"|no se puede enviar a la dirección",
    re.IGNORECASE,
)

_TLD_CURRENCY = {
    "amazon.com": "USD",
    "amazon.de": "EUR",
    "amazon.at": "EUR",
    "amazon.fr": "EUR",
    "amazon.es": "EUR",
    "amazon.it": "EUR",
    "amazon.nl": "EUR",
    "amazon.co.uk": "GBP",
}

# Tried in order; first match wins
_PRICE_SELECTORS = [
    ".priceToPay",  # primary — JS-free current price
    "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
    "#apex_desktop .a-price .a-offscreen",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "#item_price",  # marketplace seller template
]

# A stale User-Agent is itself a bot signal, and client hints that disagree with
# the UA string are a stronger one — so each entry carries its own matching hints.
_BROWSERS = [
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        ),
        "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        ),
        "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/18.5 Safari/605.1.15"
        ),
    },
]


class BotBlockedError(ScrapingError):
    """Amazon served a bot challenge we could not clear."""


class AmazonScraper(BaseScraper):
    # Delay range in seconds between requests to avoid bot detection
    _DELAY = (3.0, 7.0)
    _TIMEOUT = 20
    # One initial attempt plus retries for a bot wall / throttling response
    _MAX_ATTEMPTS = 3

    # Cookies (including the ones handed out by clearing a bot wall) are worth
    # far more than a fresh connection: get_scraper() builds a new scraper per
    # product, so sessions are shared per-host across all instances.
    _sessions: dict[str, requests.Session] = {}
    # Hosts whose session already ships to SHIP_TO_COUNTRY
    _located_hosts: set[str] = set()
    # Browser profiles (indexes into _BROWSERS) each host's sessions have used
    _browsers_tried: dict[str, set[int]] = {}

    # Language header keyed by TLD
    _ACCEPT_LANG = {
        "amazon.de": "de-DE,de;q=0.9,en;q=0.8",
        "amazon.at": "de-AT,de;q=0.9,en;q=0.8",
        "amazon.fr": "fr-FR,fr;q=0.9,en;q=0.8",
        "amazon.es": "es-ES,es;q=0.9,en;q=0.8",
        "amazon.it": "it-IT,it;q=0.9,en;q=0.8",
        "amazon.nl": "nl-NL,nl;q=0.9,en;q=0.8",
        "amazon.co.uk": "en-GB,en;q=0.9",
        "amazon.com": "en-US,en;q=0.9",
    }

    @staticmethod
    def _host(url: str) -> str:
        return (urlparse(url).hostname or "").removeprefix("www.")

    @classmethod
    def _session(cls, url: str) -> requests.Session:
        """Session for this host, reused across scraper instances."""
        host = cls._host(url)
        session = cls._sessions.get(host)
        if session is not None:
            return session

        # A browser profile Amazon has refused the location picker to is not
        # reused until every other one has had its turn.
        tried = cls._browsers_tried.setdefault(host, set())
        if len(tried) >= len(_BROWSERS):
            tried.clear()
        choice = random.choice([i for i in range(len(_BROWSERS)) if i not in tried])
        tried.add(choice)

        session = requests.Session()
        session.headers.update(
            {
                **_BROWSERS[choice],
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,image/apng,*/*;q=0.8"
                ),
                "Accept-Language": cls._ACCEPT_LANG.get(host, "en-US,en;q=0.9"),
                "Accept-Encoding": "gzip, deflate, br",
                "Upgrade-Insecure-Requests": "1",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            }
        )
        cls._sessions[host] = session
        return session

    @staticmethod
    def _bot_wall_form(soup: BeautifulSoup):
        """The interstitial's form, if Amazon served a bot challenge."""
        return soup.select_one('form[action*="validateCaptcha"]')

    def _clear_bot_wall(self, session: requests.Session, url: str, form) -> bool:
        """Submit the "continue shopping" interstitial to earn captcha cookies.

        Amazon's soft wall ships its own answer in a hidden `field-keywords`
        input, so replaying the form is enough. A real image captcha has no
        answer in the markup — that we cannot clear.
        """
        fields = {
            inp["name"]: inp.get("value", "") for inp in form.select("input[name]")
        }
        if not fields.get("field-keywords"):
            return False

        # Send us back to the product page rather than the site root
        fields["amzn-r"] = urlparse(url).path or "/"
        resp = session.get(
            urljoin(url, form.get("action")),
            params=fields,
            headers={"Referer": url, "Sec-Fetch-Site": "same-origin"},
            timeout=self._TIMEOUT,
        )
        return resp.ok

    def _set_ship_to(self, session: requests.Session, url: str, soup) -> bool:
        """Point the session's delivery location at SHIP_TO_COUNTRY.

        Amazon's location picker is a two-step exchange an anonymous session is
        allowed to make: the product page carries a CSRF header that renders the
        picker, and the rendered picker carries a second token that authorises
        the change. The result lives in the session cookies, so every later
        page in this session is priced for that country.
        """
        trigger = soup.select_one("#nav-global-location-data-modal-action")
        if trigger is None:
            return False
        try:
            modal = json.loads(trigger.get("data-a-modal") or "")
        except json.JSONDecodeError:
            return False
        modal_path = modal.get("url")
        modal_headers = modal.get("ajaxHeaders") or {}
        if not modal_path or not modal_headers:
            return False

        ajax = {
            "Referer": url,
            "Accept": "text/html,*/*",
            "X-Requested-With": "XMLHttpRequest",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }
        resp = session.get(
            urljoin(url, modal_path),
            headers={**modal_headers, **ajax},
            timeout=self._TIMEOUT,
        )
        token = re.search(r'CSRF_TOKEN\s*:\s*"([^"]+)"', resp.text)
        if not resp.ok or token is None:
            return False

        resp = session.post(
            urljoin(url, _GLOW_CHANGE_PATH),
            params={"actionSource": "glow"},
            data={
                "locationType": "COUNTRY",
                "district": SHIP_TO_COUNTRY,
                "countryCode": SHIP_TO_COUNTRY,
                "deviceType": "web",
                "storeContext": "generic",
                "pageType": "Detail",
                "actionSource": "glow",
            },
            headers={"anti-csrftoken-a2z": token.group(1), **ajax},
            timeout=self._TIMEOUT,
        )
        if not resp.ok:
            return False
        try:
            return bool(resp.json().get("isAddressUpdated"))
        except ValueError:
            return False

    @staticmethod
    def undeliverable(soup) -> bool:
        """True when the page says the item will not ship to the chosen location.

        A page with several sellers repeats the delivery block once per offer;
        the first is the selected offer, the one whose price we read.
        """
        for selector in ("#deliveryBlockMessage", "#availability"):
            block = soup.select_one(selector)
            if block and _UNDELIVERABLE.search(block.get_text(" ", strip=True)):
                return True
        return False

    @staticmethod
    def sizes(soup) -> tuple[dict | None, list[dict]]:
        """The size this page is for, and every size the listing offers.

        Shoe listings carry a size dropdown whose options name a child ASIN
        each; the selected one is the ASIN we were asked for. Returns
        (selected, all) with each size as {"eu"/"us", "width", "asin",
        "available"}; (None, []) for a listing without sizes.
        """
        selected = None
        sizes = []
        # Older layout: a native <select> whose option values are "index,ASIN"
        for option in soup.select("select#native_dropdown_selected_size_name option"):
            value = option.get("value") or ""
            if "," not in value:
                continue
            classes = " ".join(option.get("class") or [])
            size = parse_amazon_size(option.get_text(strip=True))
            size["asin"] = value.split(",", 1)[1]
            size["available"] = "Unavailable" not in classes
            sizes.append(size)
            if "Select" in classes:
                selected = size
        if sizes:
            return selected, sizes
        # Newer layout: one swatch per size, ASIN on the swatch, state on the
        # button inside it
        for swatch in soup.select(
            "#inline-twister-row-size_name li.inline-twister-swatch[data-asin]"
        ):
            label = swatch.get_text(" ", strip=True)
            if not re.search(r"\d", label):
                continue
            button = swatch.select_one("[id^='size_name_']")
            classes = " ".join(
                (swatch.get("class") or []) + ((button.get("class") if button else None) or [])
            ).lower()
            size = parse_amazon_size(label)
            size["asin"] = swatch["data-asin"]
            size["available"] = "unavailable" not in classes
            sizes.append(size)
            if "a-button-selected" in classes:
                selected = size
        return selected, sizes

    @staticmethod
    def ship_to_location(soup) -> str:
        """The delivery location Amazon rendered the page for, as shown in the header."""
        tag = soup.select_one("#glow-ingress-line2")
        return tag.get_text(strip=True) if tag else ""

    def _fetch_page(self, session: requests.Session, url: str) -> BeautifulSoup:
        """One page through the bot wall and throttling retries."""
        blocked = False

        for attempt in range(self._MAX_ATTEMPTS):
            # Grows with each retry so throttling gets a chance to expire
            low, high = self._DELAY
            time.sleep(random.uniform(low, high) * (attempt + 1))

            resp = session.get(url, timeout=self._TIMEOUT)
            if resp.status_code in (429, 503):
                blocked = True
                continue
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            form = self._bot_wall_form(soup)
            if form is None:
                return soup

            blocked = True
            if not self._clear_bot_wall(session, url, form):
                raise BotBlockedError(f"Amazon served an unsolvable captcha for {url}")

        if blocked:
            # Drop the burned session so the next product starts clean
            host = self._host(url)
            self._sessions.pop(host, None)
            self._located_hosts.discard(host)
            raise BotBlockedError(
                f"Amazon kept blocking {url} after {self._MAX_ATTEMPTS} attempts"
            )
        raise ScrapingError(f"Could not fetch {url}")

    def fetch(self, url: str) -> BeautifulSoup:
        session = self._session(url)
        host = self._host(url)
        soup = self._fetch_page(session, url)
        if host in self._located_hosts:
            return soup

        # First real page in this session: relocate, then re-read the page so
        # the price reflects the new country. Amazon serves some browser
        # profiles a sign-in-only location picker, consistently, so a refusal
        # means starting over as a different browser rather than retrying.
        for _ in range(len(_BROWSERS)):
            if self._set_ship_to(session, url, soup):
                self._located_hosts.add(host)
                return self._fetch_page(session, url)
            self._sessions.pop(host, None)
            session = self._session(url)
            soup = self._fetch_page(session, url)

        # Not fatal — a price for the wrong country still beats no price — but
        # loud, since every price this run is then for the wrong place.
        self._located_hosts.add(host)
        print(
            f"⚠️ could not set delivery location to {SHIP_TO_COUNTRY} for {host} "
            f"with any browser profile; pricing as "
            f"{self.ship_to_location(soup) or 'unknown'}",
            file=sys.stderr,
        )
        return soup

    def scrape(self, url: str) -> dict:
        soup = self.fetch(url)

        currency = _TLD_CURRENCY.get(self._host(url), "EUR")

        name_tag = soup.select_one("#productTitle")
        name = name_tag.get_text(strip=True) if name_tag else ""
        size, sizes = self.sizes(soup)
        size_info = {"size": size, "sizes": sizes} if sizes else {}

        # A price we cannot buy at is not a price. Same shape as a sold-out
        # page, so a listing that later opens up to Austria triggers the
        # restock notice.
        if name and self.undeliverable(soup):
            return {
                "name": name,
                "price": None,
                "currency": currency,
                "in_stock": False,
                **size_info,
            }

        for selector in _PRICE_SELECTORS:
            tag = soup.select_one(selector)
            if tag:
                try:
                    return {
                        "name": name,
                        "price": self.parse_price(tag.get_text()),
                        "currency": currency,
                        **size_info,
                    }
                except ValueError:
                    continue

        # JSON-LD fallback (Amazon embeds it on some pages)
        result = self._from_jsonld(soup)
        if result:
            result["name"] = result["name"] or name
            result.setdefault("currency", currency)
            result.update(size_info)
            return result

        # A rendered product page with no buy-box price means the item is
        # unavailable — sold out, or not deliverable to this region. That is a
        # fact about the product, not a scraping failure, so report it as
        # out of stock and let a later restock notify. A title is the proof the
        # page really rendered: a bot wall or broken selector has none.
        if name:
            return {
                "name": name,
                "price": None,
                "currency": currency,
                "in_stock": False,
                **size_info,
            }

        raise ScrapingError(f"Could not extract Amazon price from {url}")

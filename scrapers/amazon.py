from urllib.parse import urljoin, urlparse
import random
import time

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, ScrapingError

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

        session = requests.Session()
        session.headers.update(
            {
                **random.choice(_BROWSERS),
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

    def fetch(self, url: str) -> BeautifulSoup:
        session = self._session(url)
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
            self._sessions.pop(self._host(url), None)
            raise BotBlockedError(
                f"Amazon kept blocking {url} after {self._MAX_ATTEMPTS} attempts"
            )
        raise ScrapingError(f"Could not fetch {url}")

    def scrape(self, url: str) -> dict:
        soup = self.fetch(url)

        currency = _TLD_CURRENCY.get(self._host(url), "EUR")

        name_tag = soup.select_one("#productTitle")
        name = name_tag.get_text(strip=True) if name_tag else ""

        for selector in _PRICE_SELECTORS:
            tag = soup.select_one(selector)
            if tag:
                try:
                    return {
                        "name": name,
                        "price": self.parse_price(tag.get_text()),
                        "currency": currency,
                    }
                except ValueError:
                    continue

        # JSON-LD fallback (Amazon embeds it on some pages)
        result = self._from_jsonld(soup)
        if result:
            result["name"] = result["name"] or name
            result.setdefault("currency", currency)
            return result

        raise ScrapingError(f"Could not extract Amazon price from {url}")

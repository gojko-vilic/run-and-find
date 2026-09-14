"""Shoe sizes: which ones the wearer wants, and which ones a store has.

Sizes are compared as labels, never converted: a store's own EU/US/cm label is
matched against the labels products.yaml lists for the same system. Brands
print different EU numbers for the same foot, so the EU list is per brand.
"""

import re
from urllib.parse import urlparse

from .base import BaseScraper

_FRACTIONS = {"⅓": " 1/3", "⅔": " 2/3", "½": ".5"}
_UNITS = re.compile(r"\b(EU|EUR|US|UK|cm)\b", re.IGNORECASE)


def norm(label) -> str:
    """'44 EU' → '44', '431/3' → '43 1/3', '⅓' → ' 1/3', '45.0' → '45'."""
    if label is None:
        return ""
    text = str(label)
    for glyph, ascii_ in _FRACTIONS.items():
        text = text.replace(glyph, ascii_)
    text = _UNITS.sub("", text)
    text = re.sub(r"(\d)(1/3|2/3)", r"\1 \2", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(\d+)\.0$", r"\1", text)
    return text


class SizeFilter:
    """The sizes worth tracking, from the ``sizes`` block of products.yaml."""

    def __init__(self, config: dict):
        self.cm = {norm(x) for x in config.get("cm") or []}
        self.us = {norm(x) for x in config.get("us") or []}
        eu = config.get("eu") or {}
        self.eu_default = {norm(x) for x in eu.get("default") or []}
        self.eu_brand = {
            brand.lower(): {norm(x) for x in labels}
            for brand, labels in eu.items()
            if brand != "default"
        }

    def eu(self, product_name: str | None) -> set[str]:
        """EU labels for the brand a product name starts with."""
        name = (product_name or "").lower()
        for brand, labels in self.eu_brand.items():
            if name.startswith(brand):
                return labels
        return self.eu_default

    def fits(self, size: dict, product_name: str | None = None) -> bool:
        """Whether one store size is a wanted one. Widths other than regular never fit."""
        if size.get("width"):
            return False
        return (
            norm(size.get("cm")) in self.cm
            or norm(size.get("us")) in self.us
            or norm(size.get("eu")) in self.eu(product_name)
        )

    def any_fits(self, sizes, product_name: str | None = None) -> bool:
        return any(self.fits(s, product_name) for s in sizes)

    def describe(self, product_name: str | None = None) -> str:
        parts = []
        if self.eu(product_name):
            parts.append("EU " + "/".join(sorted(self.eu(product_name))))
        if self.us:
            parts.append("US " + "/".join(sorted(self.us)))
        if self.cm:
            parts.append("/".join(sorted(self.cm)) + " cm")
        return ", ".join(parts)


# ── Per-store parsers: available sizes on a product page ─────────────────────
# Each returns a list of {"eu"/"us"/"cm": label, "width": "" | "wide"} for the
# sizes a customer can put in the basket right now.


def _sportvision(soup, url: str) -> list[dict]:
    sizes = []
    for li in soup.select("ul.product-attributes li"):
        if "disabled" in (li.get("class") or []):
            continue
        # The tooltip carries every system: "Veličina: 10.5<br />Veličina EU: 44.5
        # <br />Veličina UK: 10<br />Veličina cm: 28.5<br />"
        tip = li.get("data-original-title") or li.get("aria-label") or ""
        size = {}
        for system, key in (("EU", "eu"), ("cm", "cm"), ("UK", "uk")):
            m = re.search(rf"Veli[čc]ina {system}:\s*([\d.,/ ⅓⅔]+)", tip)
            if m:
                size[key] = norm(m.group(1))
        # The bare "Veličina" is the brand's home system — UK for Mizuno, US
        # for Nike — so it is not comparable and not kept.
        if not size:
            eu = li.select_one(".eur-size")
            cm = li.select_one(".cm-size")
            if eu:
                size["eu"] = norm(eu.get_text())
            if cm:
                size["cm"] = norm(cm.get_text())
        if size:
            sizes.append(size)
    return sizes


def _runnmore(soup, url: str) -> list[dict]:
    # The page also renders related products, each with its own size list; the
    # one for this product carries the product id from the URL.
    m = re.search(r"/(\d+)-", urlparse(url).path)
    lst = soup.find(id=m.group(1)) if m else None
    if lst is None or "nb-product-size-list" not in " ".join(lst.get("class") or []):
        detail = soup.select_one("[class*='product-detail-info']")
        lst = detail.select_one("[class*='nb-product-size-list']") if detail else None
    if lst is None:
        return []
    sizes = []
    for box in lst.select("[class*='nb-size-value-box']"):
        if "disabled" in (box.get("class") or []):
            continue
        # data-productsize-name is the brand's home-system size (UK for
        # Mizuno), so only the EU label shown to the customer is comparable.
        label = box.select_one("[class*='nb-size-value-span']")
        sizes.append({"eu": norm(label.get_text()) if label else ""})
    return sizes


def _intersport(soup, url: str) -> list[dict]:
    # Only sizes in stock are rendered at all
    return [
        {"eu": norm(inp["data-size"])}
        for inp in soup.select("ul.size-list input[data-size]")
    ]


_STORES = {
    "sportvision.rs": _sportvision,
    "runnmore.com": _runnmore,
    "intersport.rs": _intersport,
}


def store_parser(url: str):
    host = (urlparse(url).hostname or "").removeprefix("www.")
    for domain, parser in _STORES.items():
        if host == domain or host.endswith("." + domain):
            return parser
    return None


def available_sizes(url: str, soup=None) -> list[dict] | None:
    """Sizes in stock at a store page, or None when the store is not understood.

    None rather than [] so an unknown store is not mistaken for a sold-out one.
    """
    parser = store_parser(url)
    if parser is None:
        return None
    if soup is None:
        soup = BaseScraper().fetch(url)
    return parser(soup, url)


def parse_amazon_size(label: str) -> dict:
    """'44.5 EU Weit' → {'eu': '44.5', 'width': 'wide'}; '10.5 Wide' → {'us': ...}."""
    text = label.strip()
    width = ""
    m = re.search(r"\b(Weit|Wide|X-Wide|Schmal|Narrow|Extra Weit)\b", text, re.IGNORECASE)
    if m:
        width = "wide" if "w" in m.group(1).lower() else "narrow"
        text = text.replace(m.group(0), "")
    # Unisex listings label a size for both: "12 Women/11 Men" — the men's
    # number is the one on the shoe's own chart.
    m = re.search(r"(\d+(?:\.\d)?)\s*Men", text)
    if m:
        return {"us": norm(m.group(1)), "width": width}
    system = "eu" if re.search(r"\bEU\b", text) else "us"
    return {system: norm(text), "width": width}

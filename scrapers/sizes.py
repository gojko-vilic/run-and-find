"""Sizes: which ones the wearer wants, and which ones a store has.

Sizes are compared as labels, never converted: a store's own EU/US/cm label is
matched against the labels products.yaml lists for the same system. Brands
print different EU numbers for the same foot, so the EU list is per brand.
Clothing is one list of letter sizes (M, L) under ``clothing``; jeans are
matched on the exact waist/length pair, per model, from the labels under
``jeans`` (product-name prefix → ["32/34"]).
"""

import json
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


def _per_name(block: dict | None, convert) -> tuple[list, dict[str, list]]:
    """A YAML mapping of product-name prefix → labels, plus its ``default`` row.

    Brands print different EU numbers for one foot and each jeans model is
    worn in its own size, so these lists are looked up by the start of the
    product name.
    """
    block = block or {}
    default = [convert(x) for x in block.get("default") or []]
    named = {
        prefix.lower(): [convert(x) for x in labels]
        for prefix, labels in block.items()
        if prefix != "default"
    }
    return default, named


def _for_name(table: tuple[list, dict[str, list]], product_name: str | None) -> list:
    default, named = table
    name = (product_name or "").lower()
    for prefix, labels in named.items():
        if name.startswith(prefix):
            return labels
    return default


def _jeans_config_label(text) -> str:
    label = jeans_label(parse_clothing_size(text))
    if not label:
        raise ValueError(f"jeans size {text!r} must be waist/length, like '32/34'")
    return label


class SizeFilter:
    """The sizes worth tracking, from the ``sizes`` block of products.yaml."""

    def __init__(self, config: dict):
        self.cm = {norm(x) for x in config.get("cm") or []}
        self.us = {norm(x) for x in config.get("us") or []}
        # Letter sizes for clothing, kept in the order written for describe().
        self.clothing = [norm(x).upper() for x in config.get("clothing") or []]
        self._eu = _per_name(config.get("eu"), norm)
        # Jeans as exact waist/length pairs per model: "32/34" is one size, not two.
        self._jeans = _per_name(config.get("jeans"), _jeans_config_label)

    def eu(self, product_name: str | None) -> list[str]:
        """EU labels for the brand a product name starts with."""
        return _for_name(self._eu, product_name)

    def jeans(self, product_name: str | None) -> list[str]:
        """Waist/length pairs for the jeans model a product name starts with."""
        return _for_name(self._jeans, product_name)

    def fits(self, size: dict, product_name: str | None = None) -> bool:
        """Whether one store size is a wanted one. Widths other than regular never fit."""
        if size.get("width"):
            return False
        return (
            norm(size.get("cm")) in self.cm
            or norm(size.get("us")) in self.us
            or norm(size.get("eu")) in self.eu(product_name)
            or norm(size.get("clothing")).upper() in self.clothing
            or jeans_label(size) in self.jeans(product_name)
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
        if self.clothing:
            parts.append("/".join(self.clothing))
        for pair in self.jeans(product_name):
            parts.append("W{}/L{}".format(*pair.split("/")))
        return ", ".join(parts)


# ── Per-store parsers: available sizes on a product page ─────────────────────
# Each returns a list of {"eu"/"us"/"cm"/"clothing": label, "width": "" | "wide"}
# (jeans: {"waist": "32", "length": "32"}) for the sizes a customer can put in
# the basket right now.

# Jeans labels: waist and length in inches, "32-032" on Fashion&Friends, "32/32" elsewhere.
_WAIST_LENGTH = re.compile(r"^\s*(\d{2})\s*[-/]\s*0?(\d{2})\s*$")


def parse_clothing_size(label) -> dict:
    """'M' → {'clothing': 'M'}; '32-032' → {'waist': '32', 'length': '32'}."""
    text = str(label or "")
    m = _WAIST_LENGTH.match(text)
    if m:
        return {"waist": m.group(1), "length": m.group(2)}
    return {"clothing": norm(text)}


def jeans_label(size: dict) -> str:
    """'waist/length' of a jeans size, '' for anything without both numbers."""
    if size.get("waist") and size.get("length"):
        return f"{norm(size['waist'])}/{norm(size['length'])}"
    return ""


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


def _find_key(obj, key: str):
    """First value under ``key`` anywhere in nested JSON, or None."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        obj = obj.values()
    elif not isinstance(obj, list):
        return None
    for value in obj:
        hit = _find_key(value, key)
        if hit is not None:
            return hit
    return None


def _magento_swatch_config(soup) -> dict | None:
    """The configurable-product JSON Magento hands its swatch renderer."""
    for script in soup.find_all("script", type="text/x-magento-init"):
        text = script.string or ""
        if "jsonConfig" not in text:
            continue
        try:
            cfg = _find_key(json.loads(text), "jsonConfig")
        except json.JSONDecodeError:
            continue
        if isinstance(cfg, dict):
            return cfg
    return None


def _fashionandfriends(soup, url: str) -> list[dict] | None:
    # Magento lists only the size children a customer can buy, each option
    # naming its child product; the theme adds stockArray with every child's
    # quantity, so a child carried at zero is dropped too. A page with no size
    # choice at all (an accessory) has nothing to filter on.
    cfg = _magento_swatch_config(soup)
    if not cfg:
        return None
    attrs = [a for a in (cfg.get("attributes") or {}).values() if a.get("code") == "size"]
    if not attrs:
        return None
    stock = cfg.get("stockArray") or {}

    def in_stock(child: str) -> bool:
        # Listed at all means salable; a quantity, when the theme gives one, must be positive.
        return child not in stock or float(stock[child] or 0) > 0

    sizes = []
    for option in attrs[0].get("options") or []:
        if any(in_stock(c) for c in option.get("products") or []):
            sizes.append(parse_clothing_size(option.get("label")))
    return sizes


_STORES = {
    "sportvision.rs": _sportvision,
    "runnmore.com": _runnmore,
    "intersport.rs": _intersport,
    "fashionandfriends.com": _fashionandfriends,
}


def store_parser(url: str):
    host = (urlparse(url).hostname or "").removeprefix("www.")
    for domain, parser in _STORES.items():
        if host == domain or host.endswith("." + domain):
            return parser
    return None


def available_sizes(url: str, soup=None) -> list[dict] | None:
    """Sizes in stock at a store page, or None when the store is not understood.

    None rather than [] so an unknown store, or a page with no size choice, is
    not mistaken for a sold-out one.
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

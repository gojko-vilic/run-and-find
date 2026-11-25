import unittest

from bs4 import BeautifulSoup

from scrapers import get_scraper
from scrapers.base import BaseScraper, ScrapingError
from scrapers.serbian import SerbianScraper

# A Magento shop: several JSON-LD blocks, the Product one priced as an
# AggregateOffer (lowPrice/highPrice, the single Offer nested inside).
AGGREGATE_OFFER = """
<script type="application/ld+json">{"@context":"http://schema.org","@type":"Store","name":"Fashion & Friends - Srbija"}</script>
<script type="application/ld+json">{"@context":"http://schema.org","@type":"Product","name":"Mu\u0161ka jakna | Wellensteyn",
 "sku":"WEMOLM-856-DO","offers":{"@type":"AggregateOffer","highPrice":"35990.00","lowPrice":"35990.00","offerCount":5,
 "availability":"InStock","priceCurrency":"RSD",
 "offers":{"@type":"Offer","availability":"InStock","priceCurrency":"RSD","price":"35990.00"}}}</script>"""


class JsonLdTest(unittest.TestCase):
    def test_aggregate_offer_price(self):
        result = BaseScraper._from_jsonld(BeautifulSoup(AGGREGATE_OFFER, "lxml"))
        self.assertEqual(
            result,
            {"name": "Muška jakna | Wellensteyn", "price": 35990.0, "currency": "RSD", "in_stock": True},
        )

# The same shop once the last size has sold: no price, offer marked out of stock.
SOLD_OUT = """
<script type="application/ld+json">{"@context":"http://schema.org","@type":"Product","name":"Mu\u0161ke farmerke | Levis 512",
 "sku":"LV28833-1304","offers":{"@type":"AggregateOffer","highPrice":"0.00","lowPrice":"0.00","offerCount":0,
 "availability":"OutOfStock","priceCurrency":"RSD"}}</script>"""


class SoldOutJsonLdTest(unittest.TestCase):
    def test_sold_out_is_not_an_error(self):
        result = BaseScraper._from_jsonld(BeautifulSoup(SOLD_OUT, "lxml"))
        self.assertEqual(
            result,
            {"name": "Muške farmerke | Levis 512", "price": None, "currency": "RSD", "in_stock": False},
        )

# Run'n'more: no structured data; the price block wraps the active price and
# two hidden ones (regular, old), so the wrapper's text is three prices run
# together.
RUNNMORE_PRICES = """
<h1>adidas Patike Adizero Adios Pro 4</h1>
<div class="nb-component nb-product-prices-3">
  <div class="nb-component nb-price nb-price-sale nb-price-active"><span class="nb-price-value">24.999,00</span><span class="nb-currency">RSD</span></div>
  <div class="nb-component nb-price nb-price-regular hidden"><span class="nb-price-value">29.999,00</span><span class="nb-currency">RSD</span></div>
  <div class="nb-component nb-price nb-price-old hidden"><span class="nb-price-value">29.999,00</span><span class="nb-currency">RSD</span></div>
</div>"""


class RunnmorePriceTest(unittest.TestCase):
    def test_reads_the_active_price_only(self):
        class Offline(SerbianScraper):
            def fetch(self, url):
                return BeautifulSoup(RUNNMORE_PRICES, "lxml")

        result = Offline().scrape("https://www.runnmore.com/patike/1-adidas-adios-pro-4")
        self.assertEqual(result["price"], 24999.0)
        self.assertEqual(result["currency"], "RSD")


# Fashion&Friends since Nov 2026: a ProductGroup that quotes nothing itself,
# every size a Product with its own Offer under hasVariant.
PRODUCT_GROUP = """
<script type="application/ld+json">{"@context":"https://schema.org","@type":"ProductGroup",
 "name":"Levis - 512 Slim Taper muške farmerke","productGroupID":"LV28833-1560","hasVariant":[
 {"@type":"Product","sku":"LV28833-1560#31-032","size":"31-032","offers":{"@type":"Offer","price":9990,
  "priceCurrency":"RSD","availability":"https://schema.org/OutOfStock"}},
 {"@type":"Product","sku":"LV28833-1560#32-034","size":"32-034","offers":{"@type":"Offer","price":10143,
  "priceCurrency":"RSD","availability":"https://schema.org/InStock"}}]}</script>"""

PRODUCT_GROUP_SOLD_OUT = """
<script type="application/ld+json">{"@context":"https://schema.org","@type":"ProductGroup",
 "name":"Levis - 512 muške farmerke","hasVariant":[
 {"@type":"Product","size":"32-034","offers":{"@type":"Offer","price":10143,
  "priceCurrency":"RSD","availability":"https://schema.org/OutOfStock"}}]}</script>"""


class ProductGroupJsonLdTest(unittest.TestCase):
    def test_price_is_the_cheapest_variant_in_stock(self):
        result = BaseScraper._from_jsonld(BeautifulSoup(PRODUCT_GROUP, "lxml"))
        self.assertEqual(
            result,
            {"name": "Levis - 512 Slim Taper muške farmerke", "price": 10143.0, "currency": "RSD", "in_stock": True},
        )

    def test_group_with_no_variant_in_stock_is_out_of_stock(self):
        result = BaseScraper._from_jsonld(BeautifulSoup(PRODUCT_GROUP_SOLD_OUT, "lxml"))
        self.assertEqual(result["price"], 10143.0)
        self.assertFalse(result["in_stock"])


def _scrape_fashionandfriends(html: str) -> dict:
    class Offline(SerbianScraper):
        def fetch(self, url):
            return BeautifulSoup(html, "lxml")

    return Offline().scrape("https://www.fashionandfriends.com/rs/levis-512-muske-farmerke-lv28833-1280/")


# A colour sold out in every size: the Product carries no offers, the page no
# price block — only the stock line says why.
FASHIONANDFRIENDS_SOLD_OUT = """
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",
 "name":"Levis - 512 muške farmerke","sku":"LV28833-1280"}</script>
<meta property="product:price:amount" content="0"/>
<div class="product-info-main"><h1>Levis - 512 muške farmerke</h1>
 <div class="product-info-stock-sku"><div class="stock unavailable" title="Raspoloživost"><span>Nije raspoloživo</span></div></div>
</div>"""

# The same page with the stock line gone too: nothing says sold out, so it is
# a page we could not read.
FASHIONANDFRIENDS_UNREADABLE = """
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",
 "name":"Levis - 512 muške farmerke","sku":"LV28833-1280"}</script>
<div class="product-info-main"><h1>Levis - 512 muške farmerke</h1></div>"""

# A discounted product's price block, with no structured data to read instead:
# the crossed-out regular price comes first, the price charged second.
FASHIONANDFRIENDS_DISCOUNTED = """
<div class="product-info-main"><h1>Levis - 512 Slim Taper muške farmerke</h1>
 <div class="product-info-price"><div class="price-box price-final_price" data-role="priceBox"></div></div>
 <div class="product-info-price"><div class="price-box">
  <span class="crossed price"><del class="crossed-price-configurable">14.490,00 RSD</del></span>
  <span class="special-price"><span class="price">10.143,00 RSD</span></span>
 </div></div>
</div>"""


class FashionAndFriendsTest(unittest.TestCase):
    def test_sold_out_page_is_out_of_stock_not_an_error(self):
        result = _scrape_fashionandfriends(FASHIONANDFRIENDS_SOLD_OUT)
        self.assertIsNone(result["price"])
        self.assertFalse(result["in_stock"])
        self.assertEqual(result["currency"], "RSD")
        self.assertEqual(result["gender"], "men")

    def test_no_price_and_no_stock_line_is_still_an_error(self):
        with self.assertRaises(ScrapingError):
            _scrape_fashionandfriends(FASHIONANDFRIENDS_UNREADABLE)

    def test_discount_reads_the_price_charged_not_the_crossed_out_one(self):
        result = _scrape_fashionandfriends(FASHIONANDFRIENDS_DISCOUNTED)
        self.assertEqual(result["price"], 10143.0)


class RegistryTest(unittest.TestCase):
    def test_fashionandfriends_is_a_serbian_store(self):
        scraper = get_scraper("https://www.fashionandfriends.com/rs/wellensteyn-x/")
        self.assertIsInstance(scraper, SerbianScraper)


if __name__ == "__main__":
    unittest.main()

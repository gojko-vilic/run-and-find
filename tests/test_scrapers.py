import unittest

from bs4 import BeautifulSoup

from scrapers import get_scraper
from scrapers.base import BaseScraper
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


class RegistryTest(unittest.TestCase):
    def test_fashionandfriends_is_a_serbian_store(self):
        scraper = get_scraper("https://www.fashionandfriends.com/rs/wellensteyn-x/")
        self.assertIsInstance(scraper, SerbianScraper)


if __name__ == "__main__":
    unittest.main()

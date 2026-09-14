import unittest

from bs4 import BeautifulSoup

from scrapers.sizes import SizeFilter, available_sizes, norm, parse_amazon_size

CONFIG = {
    "cm": ["28.5", "29"],
    "us": ["10.5", "11"],
    "eu": {
        "default": ["44.5", "45"],
        "adidas": ["44 2/3", "45 1/3"],
        "hoka": ["44 2/3", "45 1/3"],
        "puma": ["44", "44.5"],
        "mizuno": ["44", "44.5"],
    },
}


class NormTest(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(norm("44.5 EU"), "44.5")
        self.assertEqual(norm("431/3"), "43 1/3")
        self.assertEqual(norm("43 ⅓"), "43 1/3")
        self.assertEqual(norm("45.0"), "45")
        self.assertEqual(norm(" 10.5 "), "10.5")
        self.assertEqual(norm(None), "")


class SizeFilterTest(unittest.TestCase):
    def setUp(self):
        self.f = SizeFilter(CONFIG)

    def test_brand_eu(self):
        self.assertTrue(self.f.fits({"eu": "44.5"}, "Nike Pegasus 42"))
        self.assertFalse(self.f.fits({"eu": "44.5"}, "HOKA Clifton 10"))
        self.assertTrue(self.f.fits({"eu": "44 2/3"}, "HOKA Clifton 10"))
        self.assertTrue(self.f.fits({"eu": "44"}, "PUMA Deviate Nitro 4"))
        self.assertTrue(self.f.fits({"eu": "44"}, "Mizuno Wave Horizon 9"))
        self.assertFalse(self.f.fits({"eu": "45"}, "Mizuno Wave Horizon 9"))

    def test_cm_and_us(self):
        self.assertTrue(self.f.fits({"eu": "43", "cm": "28.5"}, "Nike X"))
        self.assertTrue(self.f.fits({"us": "11"}, "HOKA X"))
        self.assertFalse(self.f.fits({"us": "10"}, "HOKA X"))

    def test_width_never_fits(self):
        self.assertFalse(self.f.fits({"eu": "44.5", "width": "wide"}, "Nike X"))

    def test_any_and_describe(self):
        self.assertTrue(self.f.any_fits([{"eu": "42"}, {"eu": "45"}], "Nike X"))
        self.assertFalse(self.f.any_fits([{"eu": "42"}], "Nike X"))
        self.assertEqual(self.f.describe("HOKA X"), "EU 44 2/3/45 1/3, US 10.5/11, 28.5/29 cm")


SPORTVISION = """
<ul class="product-attributes">
  <li class="ease" data-original-title="Veličina: 10.5&lt;br /&gt;Veličina EU: 44.5&lt;br /&gt;Veličina UK: 10&lt;br /&gt;Veličina cm: 28.5&lt;br /&gt;">
    <span class="original-size">10.5</span><span class="eur-size">44.5</span><span class="cm-size">28.5</span></li>
  <li class="ease disabled" data-original-title="Obavesti me kada je veličina dostupna">
    <span class="original-size">11</span><span class="eur-size">45</span><span class="cm-size">29</span></li>
  <li class="ease"><span class="original-size">9</span><span class="eur-size">43</span><span class="cm-size">27.5</span></li>
</ul>"""

RUNNMORE = """
<div class="product-detail-info-with-cta-1">
  <div id="69865045" class="nb-component nb-product-size-list-1">
    <div class="nb-size-value nb-size-value-box-1" data-productsize-name="10.5"><span class="nb-size-value-span">44.5</span></div>
    <div class="nb-size-value nb-size-value-box-1 disabled" data-productsize-name="11"><span class="nb-size-value-span">45</span></div>
  </div>
</div>
<div class="card-body">
  <div id="69819040" class="nb-component nb-product-size-list-1">
    <div class="nb-size-value nb-size-value-box-1" data-productsize-name="11"><span class="nb-size-value-span">45</span></div>
  </div>
</div>"""

INTERSPORT = """
<ul class="size-list"><li><input class="fnc-product-cart-size" data-size="42"><div>42</div></li>
<li><input class="fnc-product-cart-size" data-size="451/3"><div>45 ⅓</div></li></ul>"""


class StoreParserTest(unittest.TestCase):
    def test_sportvision(self):
        sizes = available_sizes(
            "https://www.sportvision.rs/patike/1-x", BeautifulSoup(SPORTVISION, "lxml")
        )
        self.assertEqual(
            sizes,
            [
                {"eu": "44.5", "uk": "10", "cm": "28.5"},
                {"eu": "43", "cm": "27.5"},
            ],
        )

    def test_runnmore_uses_the_url_product_list(self):
        sizes = available_sizes(
            "https://www.runnmore.com/patike/69865045-mizuno", BeautifulSoup(RUNNMORE, "lxml")
        )
        self.assertEqual(sizes, [{"eu": "44.5"}])

    def test_intersport(self):
        sizes = available_sizes(
            "https://www.intersport.rs/x.html", BeautifulSoup(INTERSPORT, "lxml")
        )
        self.assertEqual(sizes, [{"eu": "42"}, {"eu": "45 1/3"}])

    def test_unknown_store_is_none(self):
        self.assertIsNone(available_sizes("https://rs.beosport.com/x", BeautifulSoup("", "lxml")))


class AmazonSizeTest(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(parse_amazon_size("44.5 EU"), {"eu": "44.5", "width": ""})
        self.assertEqual(parse_amazon_size("44.5 EU Weit"), {"eu": "44.5", "width": "wide"})
        self.assertEqual(parse_amazon_size("10.5"), {"us": "10.5", "width": ""})
        self.assertEqual(parse_amazon_size("10.5 Wide"), {"us": "10.5", "width": "wide"})
        self.assertEqual(parse_amazon_size("11 X-Wide"), {"us": "11", "width": "wide"})
        self.assertEqual(parse_amazon_size("12 Women/11 Men"), {"us": "11", "width": ""})
        self.assertEqual(parse_amazon_size("12.5 Women/11 Men"), {"us": "11", "width": ""})


if __name__ == "__main__":
    unittest.main()


DROPDOWN = """
<select id="native_dropdown_selected_size_name">
  <option value="-1">Auswählen</option>
  <option value="0,B0AAAAAAA1" class="dropdownUnavailable">44 EU</option>
  <option value="1,B0AAAAAAA2" class="dropdownSelect">44.5 EU</option>
  <option value="2,B0AAAAAAA3" class="dropdownAvailable">44.5 EU Weit</option>
</select>"""

INLINE = """
<div id="inline-twister-row-size_name"><ul>
  <li class="inline-twister-swatch" data-asin="B0BBBBBBBB1"><span id="size_name_0" class="a-button a-button-toggle">44 EU</span></li>
  <li class="inline-twister-swatch" data-asin="B0BBBBBBBB2"><span id="size_name_1" class="a-button a-button-selected">44.5 EU</span></li>
  <li class="inline-twister-swatch" data-asin="B0BBBBBBBB3"><span id="size_name_2" class="a-button a-button-unavailable">45 EU</span></li>
  <li class="inline-twister-swatch aok-hidden" data-asin="B0BBBBBBBB4">Verfügbare Optionen anzeigen</li>
</ul></div>"""


class AmazonSizesTest(unittest.TestCase):
    def test_dropdown(self):
        from scrapers.amazon import AmazonScraper

        selected, sizes = AmazonScraper.sizes(BeautifulSoup(DROPDOWN, "lxml"))
        self.assertEqual(selected["asin"], "B0AAAAAAA2")
        self.assertEqual([(z["eu"], z["width"], z["available"]) for z in sizes],
                         [("44", "", False), ("44.5", "", True), ("44.5", "wide", True)])

    def test_inline_twister(self):
        from scrapers.amazon import AmazonScraper

        selected, sizes = AmazonScraper.sizes(BeautifulSoup(INLINE, "lxml"))
        self.assertEqual(selected["asin"], "B0BBBBBBBB2")
        self.assertEqual([(z["eu"], z["available"]) for z in sizes],
                         [("44", True), ("44.5", True), ("45", False)])

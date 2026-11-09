import unittest

import checker
from scrapers.sizes import SizeFilter

SIZES = {"eu": {"default": ["44.5", "45"]}}


class Stub:
    def __init__(self, result):
        self.result = result

    def scrape(self, url):
        return dict(self.result)


# Amazon fell back to the listing's default child: the ASIN we track is not
# among the sizes any more, and no size we want is offered at all.
VANISHED = {
    "name": "Nike Vaporfly 4",
    "price": None,
    "currency": "EUR",
    "in_stock": False,
    "size": {"eu": "39", "asin": "B0GWZ33NZ3", "available": True},
    "sizes": [
        {"eu": "39", "asin": "B0GWZ33NZ3", "available": True},
        {"eu": "40", "asin": "B0GWZBN8MG", "available": True},
    ],
}

# Our ASIN is in the listing, it is just the wrong size.
WRONG_SIZE = {
    "name": "adidas Evo SL",
    "price": 120.0,
    "currency": "EUR",
    "size": {"eu": "42", "asin": "B0DNNVKBR8", "available": True},
    "sizes": [
        {"eu": "42", "asin": "B0DNNVKBR8", "available": True},
        {"eu": "45", "asin": "B0DNNTQSLR", "available": True},
    ],
}


class VanishedChildTest(unittest.TestCase):
    def test_tracked_as_out_of_stock_and_said_once(self):
        url = "https://www.amazon.de/dp/B0GWZNDHLG"
        prices, errors = {}, []
        checker._process_single(url, "Vaporfly 4 (44.5)", Stub(VANISHED), prices, errors, None, SizeFilter(SIZES))
        self.assertEqual(prices[url]["in_stock"], False)
        self.assertEqual(len(errors), 1, errors)

        errors.clear()
        checker._process_single(url, "Vaporfly 4 (44.5)", Stub(VANISHED), prices, errors, None, SizeFilter(SIZES))
        self.assertEqual(errors, [])
        self.assertEqual(prices[url]["in_stock"], False)

    def test_wrong_size_child_stays_a_configuration_error(self):
        url = "https://www.amazon.de/dp/B0DNNVKBR8"
        prices, errors = {}, []
        checker._process_single(url, "Evo SL", Stub(WRONG_SIZE), prices, errors, None, SizeFilter(SIZES))
        self.assertNotIn(url, prices)
        self.assertEqual(len(errors), 1)
        self.assertIn("B0DNNTQSLR", errors[0])


if __name__ == "__main__":
    unittest.main()

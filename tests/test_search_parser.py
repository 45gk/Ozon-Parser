from __future__ import annotations

import json
import unittest
from decimal import Decimal
from pathlib import Path

from ozon_parser.search import (
    OzonSearchError,
    OzonSearchParseError,
    build_search_api_url,
    parse_search_json,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "search_macbook.json"
SEARCH_URL = (
    "https://www.ozon.ru/category/noutbuki-15692/apple-26303000/"
    "?brand_was_predicted=true&category_was_predicted=true"
    "&deny_category_prediction=true&from_global=true&text=macbook+air+m5"
)


class SearchParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = FIXTURE.read_text(encoding="utf-8")
        cls.result = parse_search_json(cls.raw, search_url=SEARCH_URL)

    def test_query_and_title(self) -> None:
        self.assertEqual(self.result.query, "macbook air m5")
        self.assertIn("macbook air m5", self.result.title or "")
        self.assertEqual(len(self.result.items), 8)
        self.assertTrue(self.result.next_page)

    def test_first_item(self) -> None:
        item = self.result.items[0]
        self.assertEqual(item.position, 1)
        self.assertEqual(item.sku, "3589144498")
        self.assertEqual(item.price, Decimal("106435"))
        self.assertIsNone(item.original_price)
        self.assertEqual(item.currency, "RUB")
        self.assertEqual(item.rating, Decimal("4.9"))
        self.assertEqual(item.review_count, 1039)
        self.assertTrue(item.product_url.startswith("https://www.ozon.ru/product/"))
        self.assertTrue(item.image_url.startswith("https://ir.ozone.ru/"))
        self.assertIn("MacBook Air 13 M5", item.name or "")

    def test_discount_and_original_price(self) -> None:
        item = self.result.items[1]
        self.assertEqual(item.price, Decimal("106170"))
        self.assertEqual(item.original_price, Decimal("157192"))
        self.assertEqual(item.discount, "−32%")
        self.assertEqual(item.currency, "RUB")

    def test_product_urls_are_canonical(self) -> None:
        for item in self.result.items:
            self.assertTrue(item.product_url.startswith("https://www.ozon.ru/product/"))
            self.assertNotIn("?", item.product_url)
            self.assertTrue(item.product_url.endswith("/"))

    def test_api_url_building(self) -> None:
        api_url = build_search_api_url(SEARCH_URL)
        self.assertTrue(
            api_url.startswith(
                "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url="
            )
        )
        self.assertIn("%2Fcategory%2Fnoutbuki-15692", api_url)
        self.assertIn("macbook%2Bair%2Bm5", api_url)

    def test_product_url_is_not_a_search_url(self) -> None:
        with self.assertRaises(OzonSearchError):
            build_search_api_url(
                "https://www.ozon.ru/product/bity-magnitnye-2684123133/"
            )

    def test_incident_payload(self) -> None:
        with self.assertRaisesRegex(OzonSearchParseError, "антибот"):
            parse_search_json({"incidentId": "incident-1"})

    def test_wrong_payload(self) -> None:
        with self.assertRaisesRegex(OzonSearchParseError, "tileGridDesktop"):
            parse_search_json({"widgetStates": {}})

    def test_broken_json(self) -> None:
        with self.assertRaisesRegex(OzonSearchParseError, "JSON"):
            parse_search_json("{not json")

    def test_accepts_dict_payload(self) -> None:
        result = parse_search_json(json.loads(self.raw), search_url=SEARCH_URL)
        self.assertEqual(len(result.items), 8)


if __name__ == "__main__":
    unittest.main()

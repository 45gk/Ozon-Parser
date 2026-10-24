from __future__ import annotations

import json
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from ozon_parser.api import parse_product_json
from ozon_parser.fetch import OzonFetchError
from ozon_parser.search import (
    OzonSearchError,
    OzonSearchParseError,
    _enrich_products,
    _fetch_product_card,
    build_search_api_url,
    build_search_query_url,
    extract_search_query,
    parse_search_json,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "search_macbook.json"
PRODUCT_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "product_response.json"
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

    def test_free_text_query_builds_search_url(self) -> None:
        url = build_search_query_url("  macbook   air m5  ")
        self.assertEqual(
            url,
            "https://www.ozon.ru/search/?text=macbook+air+m5&from_global=true",
        )
        self.assertEqual(extract_search_query(url), "macbook air m5")

    def test_free_text_query_is_normalized(self) -> None:
        url = build_search_query_url("Apple MacBook Air 13 M5")
        self.assertEqual(
            url,
            "https://www.ozon.ru/search/?text=Apple+MacBook+Air+13+M5&from_global=true",
        )

    def test_too_short_query_is_rejected(self) -> None:
        with self.assertRaisesRegex(OzonSearchError, "название"):
            build_search_query_url("x")

    def test_extract_query_from_category_url(self) -> None:
        self.assertEqual(extract_search_query(SEARCH_URL), "macbook air m5")
        self.assertIsNone(extract_search_query("https://www.ozon.ru/category/1/"))

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


class SearchProductEnrichmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.search = parse_search_json(
            FIXTURE.read_text(encoding="utf-8"), search_url=SEARCH_URL
        )
        cls.item = cls.search.items[0]
        cls.product_raw = PRODUCT_FIXTURE.read_text(encoding="utf-8")
        cls.product = parse_product_json(
            cls.product_raw, source_url=cls.item.product_url
        )

    def test_fetch_product_card_uses_api_payload(self) -> None:
        with patch(
            "ozon_parser.search._fetch_api_in_page",
            return_value=(200, self.product_raw),
        ):
            product = _fetch_product_card(
                object(),
                self.item.product_url,
                headless=False,
                challenge_timeout=1,
            )
        self.assertEqual(product.sku, "2684123133")
        self.assertEqual(product.name, "Биты магнитные, усиленные для шуруповерта")

    def test_enrichment_keeps_one_failed_card(self) -> None:
        with patch(
            "ozon_parser.search._fetch_product_card",
            side_effect=[self.product, OzonFetchError("Ozon API вернул HTTP 404")],
        ):
            items = _enrich_products(
                object(),
                (
                    replace(self.item, position=1),
                    replace(self.item, position=2),
                ),
                headless=False,
                challenge_timeout=1,
            )
        self.assertIsNotNone(items[0].product)
        self.assertIsNone(items[0].product_error)
        self.assertIsNone(items[1].product)
        self.assertIn("404", items[1].product_error or "")

    def test_blocking_error_stops_card_requests(self) -> None:
        with patch(
            "ozon_parser.search._fetch_product_card",
            side_effect=OzonFetchError("HTTP 403, антибот"),
        ) as fetch:
            items = _enrich_products(
                object(),
                (
                    replace(self.item, position=1),
                    replace(self.item, position=2),
                ),
                headless=False,
                challenge_timeout=1,
            )
        self.assertEqual(fetch.call_count, 1)
        self.assertIn("403", items[0].product_error or "")
        self.assertEqual(items[0].product_error, items[1].product_error)


if __name__ == "__main__":
    unittest.main()

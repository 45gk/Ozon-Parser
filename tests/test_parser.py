from __future__ import annotations

import json
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import httpx

from ozon_parser import (
    OzonFetchError,
    OzonProductParseError,
    build_api_url,
    fetch_product_api,
    parse_product_html,
    parse_product_json,
)
from ozon_parser.cli import _build_parser, main as cli_main

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "json_responce.json"
PRODUCT_URL = (
    "https://www.ozon.ru/product/bity-magnitnye-usilennye-dlya-shurupoverta-2684123133/"
)


class JsonApiParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = FIXTURE.read_text(encoding="utf-8")
        cls.product = parse_product_json(cls.raw, source_url=PRODUCT_URL)

    def test_core_fields(self) -> None:
        product = self.product
        self.assertEqual(product.name, "Биты магнитные, усиленные для шуруповерта")
        self.assertEqual(product.sku, "2684123133")
        self.assertEqual(product.currency, "RUB")
        self.assertEqual(product.rating, Decimal("4.9"))
        self.assertEqual(product.review_count, 39852)
        self.assertTrue(product.in_stock)
        self.assertEqual(product.availability, "https://schema.org/InStock")
        self.assertEqual(product.seller, "BestPick")

    def test_prices(self) -> None:
        product = self.product
        self.assertEqual(product.price, Decimal("251"))
        self.assertEqual(product.card_price, Decimal("236"))
        self.assertEqual(product.original_price, Decimal("999"))

    def test_images(self) -> None:
        self.assertEqual(len(self.product.image_urls), 6)
        self.assertEqual(
            self.product.image_urls[0],
            "https://ir-20.ozone.ru/s3/multimedia-1-1/15179100805.jpg",
        )
        self.assertTrue(
            all(url.startswith("https://") for url in self.product.image_urls)
        )

    def test_characteristics(self) -> None:
        self.assertEqual(
            self.product.characteristics,
            {
                "Тип": "Бита",
                "Тип биты": "Односторонняя",
                "Тип наконечника": "PH2",
                "Патрон/шпиндель/крепление": "Шестигранник",
                "Размер головки, дюйм": '1/4"',
            },
        )

    def test_optional_description_brand_and_out_of_stock(self) -> None:
        payload = {
            "widgetStates": {
                "webProductHeading-1-default-1": json.dumps({"title": "Товар"}),
                "webPrice-1-default-1": json.dumps(
                    {
                        "price": "1 234,50 ₽",
                        "cardPrice": "1 100 ₽",
                        "isAvailable": False,
                    }
                ),
                "webDescription-1-default-1": json.dumps({"text": "Описание товара"}),
                "webBrand-1-default-1": json.dumps({"title": "Бренд"}),
            },
            "seo": {
                "link": [
                    {
                        "rel": "canonical",
                        "href": "https://www.ozon.ru/product/tovar-1/",
                    }
                ]
            },
        }
        product = parse_product_json(payload)
        self.assertEqual(product.price, Decimal("1234.50"))
        self.assertEqual(product.card_price, Decimal("1100"))
        self.assertEqual(product.currency, "RUB")
        self.assertFalse(product.in_stock)
        self.assertEqual(product.availability, "https://schema.org/OutOfStock")
        self.assertEqual(product.description, "Описание товара")
        self.assertEqual(product.brand, "Бренд")
        self.assertEqual(product.source_url, "https://www.ozon.ru/product/tovar-1/")

    def test_currency_falls_back_to_canonical_domain(self) -> None:
        payload = {
            "widgetStates": {
                "webPrice-1-default-1": json.dumps({"price": 199, "isAvailable": True})
            },
            "seo": {
                "link": [
                    {
                        "rel": "canonical",
                        "href": "https://www.ozon.kz/product/tovar-1/",
                    }
                ]
            },
        }
        product = parse_product_json(payload)
        self.assertEqual(product.price, Decimal("199"))
        self.assertEqual(product.currency, "KZT")
        self.assertEqual(product.source_url, "https://www.ozon.kz/product/tovar-1/")

    def test_accepts_already_decoded_widget_states(self) -> None:
        payload = json.loads(self.raw.strip("`"))
        payload["widgetStates"] = {
            key: json.loads(value) if isinstance(value, str) else value
            for key, value in payload["widgetStates"].items()
        }
        product = parse_product_json(payload)
        self.assertEqual(product.sku, "2684123133")
        self.assertEqual(product.price, Decimal("251"))


class ApiUrlTests(unittest.TestCase):
    def test_builds_entrypoint_url_from_product_link(self) -> None:
        api_url = build_api_url("https://www.ozon.ru/product/slug-123/?at=abc&sh=def")
        self.assertEqual(
            api_url,
            "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2"
            "?url=%2Fproduct%2Fslug-123%2F%3Fat%3Dabc%26sh%3Ddef",
        )

    def test_rejects_non_product_link(self) -> None:
        with self.assertRaises(OzonFetchError):
            build_api_url("https://www.ozon.ru/category/bity-10119/")

    def test_rejects_foreign_host(self) -> None:
        with self.assertRaises(OzonFetchError):
            build_api_url("https://example.com/product/slug-123/")


class ApiFetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(FIXTURE.read_text(encoding="utf-8").strip("`"))

    def _fetch(self, transport: httpx.BaseTransport):
        real_client = httpx.Client

        def factory(**kwargs):
            return real_client(transport=transport, **kwargs)

        with patch("ozon_parser.api.httpx.Client", side_effect=factory):
            return fetch_product_api(PRODUCT_URL, timeout=1)

    def test_successful_response_is_parsed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertTrue(
                request.url.path.endswith("/entrypoint-api.bx/page/json/v2")
            )
            self.assertIn("url=", request.url.query.decode())
            return httpx.Response(200, json=self.payload)

        product = self._fetch(httpx.MockTransport(handler))
        self.assertEqual(product.sku, "2684123133")
        self.assertEqual(product.price, Decimal("251"))
        self.assertEqual(product.seller, "BestPick")

    def test_antibot_response_is_reported(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(403, json={"incidentId": "incident-1"})
        )
        with self.assertRaisesRegex(OzonFetchError, "антибот"):
            self._fetch(transport)


class JsonErrorsTests(unittest.TestCase):
    def test_incident_payload_is_reported(self) -> None:
        with self.assertRaisesRegex(OzonProductParseError, "антибот"):
            parse_product_json({"incidentId": "incident-1"})

    def test_non_entrypoint_payload_is_reported(self) -> None:
        with self.assertRaisesRegex(OzonProductParseError, "widgetStates"):
            parse_product_json({"layout": []})

    def test_broken_json_is_reported(self) -> None:
        with self.assertRaisesRegex(OzonProductParseError, "JSON"):
            parse_product_json("{not json")


class HtmlParserTests(unittest.TestCase):
    def test_json_ld_and_open_graph(self) -> None:
        html = """
        <html><head>
        <meta property="og:title" content="Fallback title">
        <script type="application/ld+json">
        {
          "@type": "Product",
          "name": "HTML product",
          "description": "HTML description",
          "sku": "42",
          "image": ["https://cdn.example/1.jpg"],
          "offers": {
            "@type": "Offer",
            "price": "199.90",
            "priceCurrency": "RUB",
            "availability": "https://schema.org/InStock"
          },
          "aggregateRating": {"ratingValue": "4.5", "reviewCount": "10"}
        }
        </script>
        </head></html>
        """
        product = parse_product_html(
            html, source_url="https://www.ozon.ru/product/x-42/"
        )
        self.assertEqual(product.name, "HTML product")
        self.assertEqual(product.description, "HTML description")
        self.assertEqual(product.sku, "42")
        self.assertEqual(product.price, Decimal("199.90"))
        self.assertEqual(product.currency, "RUB")
        self.assertEqual(product.rating, Decimal("4.5"))
        self.assertEqual(product.review_count, 10)
        self.assertEqual(product.image_urls, ("https://cdn.example/1.jpg",))
        self.assertIsNone(product.in_stock)


class CliTests(unittest.TestCase):
    def test_browser_options(self) -> None:
        args = _build_parser().parse_args(
            [
                "--source",
                "browser",
                "--cdp-url",
                "http://127.0.0.1:9222",
                "--headless",
                PRODUCT_URL,
            ]
        )
        self.assertEqual(args.source, "browser")
        self.assertEqual(args.cdp_url, "http://127.0.0.1:9222")
        self.assertTrue(args.headless)

    def test_json_file_mode(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            cli_main(["--json", str(FIXTURE), PRODUCT_URL])
        data = json.loads(stdout.getvalue())
        self.assertEqual(data["sku"], "2684123133")
        self.assertEqual(data["price"], "251")
        self.assertEqual(data["currency"], "RUB")


if __name__ == "__main__":
    unittest.main()

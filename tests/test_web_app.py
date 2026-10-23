from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

_TEST_DIR = Path(tempfile.mkdtemp(prefix="ozon-web-tests-"))
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_TEST_DIR / 'test.db'}"
os.environ["CDP_URL"] = "http://127.0.0.1:9222"

from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import create_app  # noqa: E402
from ozon_parser import OzonFetchError, OzonProduct  # noqa: E402

PRODUCT_URL = (
    "https://www.ozon.ru/product/bity-magnitnye-usilennye-dlya-shurupoverta-2684123133/"
)

FAKE_PRODUCT = OzonProduct(
    source_url=PRODUCT_URL,
    name="Тестовый товар",
    description="Описание тестового товара",
    price=Decimal("199.90"),
    currency="RUB",
    availability="https://schema.org/InStock",
    rating=Decimal("4.5"),
    review_count=10,
    sku="123456",
    image_urls=("https://cdn.example/1.jpg", "https://cdn.example/2.jpg"),
    original_price=Decimal("299"),
    card_price=Decimal("189"),
    in_stock=True,
    seller="Test Seller",
    brand="Test Brand",
    characteristics={"Цвет": "Чёрный", "Материал": "Металл"},
)


def _wait_for_run(client: TestClient, run_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        if response.status_code == 200:
            data = response.json()
            if data["status"] in {"success", "failed"}:
                return data
        time.sleep(0.02)
    raise AssertionError(f"Run {run_id} did not finish in {timeout} seconds")


class WebAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def test_health(self) -> None:
        with TestClient(create_app()) as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_create_run_and_history(self) -> None:
        with TestClient(create_app()) as client:
            with patch("app.services.runner._parse_product", return_value=FAKE_PRODUCT):
                response = client.post(
                    "/api/runs",
                    json={"url": PRODUCT_URL, "source": "cdp", "timeout": 30},
                )
                self.assertEqual(response.status_code, 202)
                run_id = response.json()["id"]
                run = _wait_for_run(client, run_id)

            self.assertEqual(run["status"], "success")
            self.assertEqual(run["name"], "Тестовый товар")
            self.assertEqual(run["sku"], "123456")
            self.assertEqual(run["price"], "199.90")
            self.assertEqual(run["rating"], "4.50")
            self.assertEqual(run["product"]["characteristics"]["Цвет"], "Чёрный")
            self.assertIsNotNone(run["duration_ms"])

            listing = client.get("/api/runs").json()
            self.assertEqual(listing["total"], 1)
            self.assertEqual(listing["items"][0]["id"], run_id)

            stats = client.get("/api/stats").json()
            self.assertEqual(stats["total"], 1)
            self.assertEqual(stats["success"], 1)
            self.assertEqual(stats["unique_products"], 1)

            index = client.get("/")
            self.assertEqual(index.status_code, 200)
            self.assertIn("Тестовый товар", index.text)
            self.assertIn("Успех", index.text)

            detail = client.get(f"/runs/{run_id}")
            self.assertEqual(detail.status_code, 200)
            self.assertIn("Тестовый товар", detail.text)
            self.assertIn("Полный JSON", detail.text)
            self.assertIn("Описание тестового товара", detail.text)

    def test_form_submission_redirects_to_detail(self) -> None:
        with TestClient(create_app()) as client:
            with patch("app.services.runner._parse_product", return_value=FAKE_PRODUCT):
                response = client.post(
                    "/runs",
                    data={
                        "url": PRODUCT_URL,
                        "source": "cdp",
                        "cdp_url": "http://127.0.0.1:9222",
                        "timeout": "30",
                        "challenge_timeout": "60",
                    },
                    follow_redirects=False,
                )
            self.assertEqual(response.status_code, 303)
            self.assertTrue(response.headers["location"].startswith("/runs/"))

    def test_failed_run_is_persisted(self) -> None:
        with TestClient(create_app()) as client:
            with patch(
                "app.services.runner._parse_product",
                side_effect=OzonFetchError("Ozon вернул 403"),
            ):
                response = client.post(
                    "/api/runs",
                    json={"url": PRODUCT_URL, "source": "api"},
                )
                run_id = response.json()["id"]
                run = _wait_for_run(client, run_id)

            self.assertEqual(run["status"], "failed")
            self.assertIn("403", run["error"])

            failed = client.get("/api/runs?status=failed").json()
            self.assertEqual(failed["total"], 1)
            self.assertEqual(failed["items"][0]["status"], "failed")

            stats = client.get("/api/stats").json()
            self.assertEqual(stats["failed"], 1)
            self.assertEqual(stats["success_rate"], 0.0)

    def test_invalid_url_is_rejected(self) -> None:
        with TestClient(create_app()) as client:
            response = client.post(
                "/api/runs",
                json={"url": "https://example.com/product/1/", "source": "api"},
            )
        self.assertEqual(response.status_code, 422)

    def test_unknown_run_returns_404(self) -> None:
        with TestClient(create_app()) as client:
            api_response = client.get("/api/runs/does-not-exist")
            page_response = client.get("/runs/does-not-exist")
        self.assertEqual(api_response.status_code, 404)
        self.assertEqual(page_response.status_code, 404)
        self.assertIn("Страница не найдена", page_response.text)

    def test_search_and_filter(self) -> None:
        with TestClient(create_app()) as client:
            with patch("app.services.runner._parse_product", return_value=FAKE_PRODUCT):
                first = client.post(
                    "/api/runs",
                    json={"url": PRODUCT_URL, "source": "cdp"},
                ).json()
                _wait_for_run(client, first["id"])

            with patch(
                "app.services.runner._parse_product",
                side_effect=OzonFetchError("blocked"),
            ):
                second = client.post(
                    "/api/runs",
                    json={"url": PRODUCT_URL, "source": "html"},
                ).json()
                _wait_for_run(client, second["id"])

            by_name = client.get("/api/runs?q=Тестовый").json()
            self.assertEqual(by_name["total"], 1)
            self.assertEqual(by_name["items"][0]["id"], first["id"])

            by_sku = client.get("/api/runs?q=123456").json()
            self.assertEqual(by_sku["total"], 1)

            by_source = client.get("/api/runs?source=html").json()
            self.assertEqual(by_source["total"], 1)
            self.assertEqual(by_source["items"][0]["status"], "failed")

    @classmethod
    def tearDownClass(cls) -> None:
        engine.dispose()
        shutil.rmtree(_TEST_DIR, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

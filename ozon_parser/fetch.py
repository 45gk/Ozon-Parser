from urllib.parse import urlparse

import httpx

from ozon_parser.parser import OzonProduct, parse_product_html
from ozon_parser.urls import is_ozon_host


class OzonFetchError(RuntimeError):
    """Raised when a public Ozon product page cannot be fetched."""


def fetch_product(url: str, timeout: float = 20.0) -> OzonProduct:
    """Fetch and parse a public Ozon page using a normal HTTP request."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not is_ozon_host(parsed.hostname):
        raise OzonFetchError("Укажи ссылку на страницу домена Ozon.")

    try:
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": "OzonProductParser/0.2 (+local CLI)"},
        )
    except httpx.HTTPError as exc:
        raise OzonFetchError(f"Не удалось загрузить страницу Ozon: {exc}") from exc

    if not is_ozon_host(urlparse(str(response.url)).hostname):
        raise OzonFetchError("Ozon перенаправил запрос за пределы домена Ozon.")
    if response.status_code in {403, 429}:
        raise OzonFetchError(
            f"Ozon ограничил запрос (HTTP {response.status_code}). "
            "Парсер не пытается обходить такие ограничения."
        )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise OzonFetchError(f"Ozon вернул HTTP {response.status_code}.") from exc

    product = parse_product_html(response.text, source_url=str(response.url))
    return product

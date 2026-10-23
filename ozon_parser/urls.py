from __future__ import annotations

from urllib.parse import urlparse

OZON_DOMAINS = ("ozon.ru", "ozon.kz", "ozon.by", "ozon.uz", "ozon.com")


def is_ozon_host(host: str | None) -> bool:
    """Return True for Ozon storefront hosts (including country subdomains)."""
    normalized = (host or "").lower().rstrip(".")
    return any(
        normalized == domain or normalized.endswith(f".{domain}")
        for domain in OZON_DOMAINS
    )


def is_product_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme in {"http", "https"}
        and is_ozon_host(parsed.hostname)
        and parsed.path.startswith("/product/")
    )

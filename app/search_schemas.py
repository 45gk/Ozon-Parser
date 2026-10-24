from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from ozon_parser.search import OzonSearchError, build_search_query_url
from ozon_parser.urls import is_search_url

SearchSource = Literal["cdp", "browser"]

_OZON_HOST_RE = re.compile(
    r"^(?:www\.)?(?:[a-z0-9-]+\.)*ozon\.(?:ru|kz|by|uz|com)(?:/|$)",
    re.IGNORECASE,
)


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme:
        return True
    return bool(_OZON_HOST_RE.match(value))


def _normalized_url(value: str) -> str:
    if "://" not in value:
        return f"https://{value}"
    return value


class SearchCreate(BaseModel):
    """Create a search from a URL or a free-text product name.

    ``url`` is kept as the single public field for backward compatibility. A
    value that is not an URL is treated as a search phrase and converted to
    ``https://www.ozon.ru/search/?text=...``.
    """

    url: str = Field(..., min_length=2, max_length=3000)
    source: SearchSource = "cdp"
    cdp_url: str | None = None
    timeout: float = Field(default=settings.default_timeout, ge=5, le=300)
    challenge_timeout: float = Field(
        default=settings.default_challenge_timeout, ge=0, le=600
    )
    limit: int = Field(default=20, ge=1, le=100)
    parse_products: bool = True
    headless: bool = False

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Введите ссылку на выдачу Ozon или название товара.")
        if _looks_like_url(value):
            normalized = _normalized_url(value)
            if not is_search_url(normalized):
                raise ValueError(
                    "Нужна ссылка на выдачу Ozon: /category/... или /search/... "
                    "Либо введите название товара без ссылки."
                )
            return normalized
        try:
            return build_search_query_url(value)
        except OzonSearchError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("cdp_url")
    @classmethod
    def validate_cdp_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("CDP URL должен начинаться с http:// или https://")
        return value.rstrip("/")


class SearchCreated(BaseModel):
    id: str
    status: str


class SearchProductOut(BaseModel):
    status: str
    name: str | None = None
    description: str | None = None
    sku: str | None = None
    price: str | None = None
    card_price: str | None = None
    original_price: str | None = None
    currency: str | None = None
    in_stock: bool | None = None
    seller: str | None = None
    brand: str | None = None
    rating: str | None = None
    review_count: int | None = None
    image_url: str | None = None
    characteristics: dict[str, str] = Field(default_factory=dict)
    data: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int | None = None
    parsed_at: datetime | None = None


class SearchItemOut(BaseModel):
    position: int
    sku: str | None = None
    product_url: str
    name: str | None = None
    price: str | None = None
    original_price: str | None = None
    currency: str | None = None
    discount: str | None = None
    rating: str | None = None
    review_count: int | None = None
    image_url: str | None = None
    product: SearchProductOut | None = None


class SearchRunSummary(BaseModel):
    id: str
    search_url: str
    query: str | None = None
    title: str | None = None
    source: str
    status: str
    items_count: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None


class SearchRunDetail(SearchRunSummary):
    items: list[SearchItemOut] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    products_count: int = 0
    products_failed: int = 0


class SearchList(BaseModel):
    items: list[SearchRunSummary]
    total: int
    limit: int
    offset: int


class SearchStats(BaseModel):
    total: int
    success: int
    failed: int
    active: int
    unique_queries: int
    total_items: int
    avg_duration_ms: int | None = None
    success_rate: float = 0.0

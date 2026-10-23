from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from ozon_parser.urls import is_product_url

Source = Literal["cdp", "browser", "api", "html"]


class RunCreate(BaseModel):
    url: str = Field(..., min_length=12, max_length=2000)
    source: Source = "cdp"
    cdp_url: str | None = None
    timeout: float = Field(default=settings.default_timeout, ge=5, le=300)
    challenge_timeout: float = Field(
        default=settings.default_challenge_timeout, ge=0, le=600
    )
    headless: bool = False

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        if not is_product_url(value):
            raise ValueError(
                "Нужна ссылка на карточку Ozon: https://www.ozon.ru/product/..."
            )
        return value

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


class RunCreated(BaseModel):
    id: str
    status: str


class RunSummary(BaseModel):
    id: str
    product_url: str
    source: str
    status: str
    name: str | None = None
    sku: str | None = None
    price: str | None = None
    currency: str | None = None
    rating: str | None = None
    review_count: int | None = None
    in_stock: bool | None = None
    seller: str | None = None
    image_url: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None


class RunDetail(RunSummary):
    product: dict[str, Any] | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class RunList(BaseModel):
    items: list[RunSummary]
    total: int
    limit: int
    offset: int


class Stats(BaseModel):
    total: int
    success: int
    failed: int
    active: int
    unique_products: int
    avg_duration_ms: int | None = None
    success_rate: float = 0.0

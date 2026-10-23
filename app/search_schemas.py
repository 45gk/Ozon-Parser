from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from ozon_parser.urls import is_ozon_host

SearchSource = Literal["cdp", "browser"]


def _is_search_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme in {"http", "https"}
        and is_ozon_host(parsed.hostname)
        and (parsed.path.startswith("/category/") or parsed.path.startswith("/search/"))
    )


class SearchCreate(BaseModel):
    url: str = Field(..., min_length=12, max_length=3000)
    source: SearchSource = "cdp"
    cdp_url: str | None = None
    timeout: float = Field(default=settings.default_timeout, ge=5, le=300)
    challenge_timeout: float = Field(
        default=settings.default_challenge_timeout, ge=0, le=600
    )
    limit: int = Field(default=20, ge=1, le=100)
    headless: bool = False

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        if not _is_search_url(value):
            raise ValueError(
                "Нужна ссылка на выдачу Ozon: /category/... или /search/..."
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


class SearchCreated(BaseModel):
    id: str
    status: str


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

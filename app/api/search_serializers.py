from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import SearchItem, SearchItemProduct, SearchRun
from app.search_schemas import (
    SearchItemOut,
    SearchProductOut,
    SearchRunDetail,
    SearchRunSummary,
)


def _stringify(value) -> str | None:
    return str(value) if value is not None else None


def _utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _product_to_out(product: SearchItemProduct) -> SearchProductOut:
    return SearchProductOut(
        status=product.status,
        name=product.name,
        description=product.description,
        sku=product.sku,
        price=_stringify(product.price),
        card_price=_stringify(product.card_price),
        original_price=_stringify(product.original_price),
        currency=product.currency,
        in_stock=product.in_stock,
        seller=product.seller,
        brand=product.brand,
        rating=_stringify(product.rating),
        review_count=product.review_count,
        image_url=product.image_url,
        characteristics=product.characteristics or {},
        data=product.data,
        error=product.error,
        duration_ms=product.duration_ms,
        parsed_at=_utc(product.parsed_at),
    )


def search_item_to_out(item: SearchItem) -> SearchItemOut:
    return SearchItemOut(
        position=item.position,
        sku=item.sku,
        product_url=item.product_url,
        name=item.name,
        price=_stringify(item.price),
        original_price=_stringify(item.original_price),
        currency=item.currency,
        discount=item.discount,
        rating=_stringify(item.rating),
        review_count=item.review_count,
        image_url=item.image_url,
        product=_product_to_out(item.product) if item.product else None,
    )


def search_run_to_summary(run: SearchRun) -> SearchRunSummary:
    return SearchRunSummary(
        id=str(run.id),
        search_url=run.search_url,
        query=run.query,
        title=run.title,
        source=run.source,
        status=run.status,
        items_count=run.items_count,
        created_at=_utc(run.created_at),
        started_at=_utc(run.started_at),
        finished_at=_utc(run.finished_at),
        duration_ms=run.duration_ms,
        error=run.error,
    )


def search_run_to_detail(run: SearchRun) -> SearchRunDetail:
    summary = search_run_to_summary(run)
    return SearchRunDetail(
        **summary.model_dump(),
        items=[search_item_to_out(item) for item in run.items],
        options=run.options or {},
        products_count=run.products_count,
        products_failed=run.products_failed,
    )

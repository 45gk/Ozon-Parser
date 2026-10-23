from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import ParseRun
from app.schemas import RunDetail, RunSummary


def _stringify(value) -> str | None:
    return str(value) if value is not None else None


def _utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def run_to_summary(run: ParseRun) -> RunSummary:
    return RunSummary(
        id=str(run.id),
        product_url=run.product_url,
        source=run.source,
        status=run.status,
        name=run.name,
        sku=run.sku,
        price=_stringify(run.price),
        currency=run.currency,
        rating=_stringify(run.rating),
        review_count=run.review_count,
        in_stock=run.in_stock,
        seller=run.seller,
        image_url=run.image_url,
        created_at=_utc(run.created_at),
        started_at=_utc(run.started_at),
        finished_at=_utc(run.finished_at),
        duration_ms=run.duration_ms,
        error=run.error,
    )


def run_to_detail(run: ParseRun) -> RunDetail:
    summary = run_to_summary(run)
    return RunDetail(
        **summary.model_dump(),
        product=run.product,
        options=run.options or {},
    )

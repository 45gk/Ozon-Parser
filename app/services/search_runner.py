from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from uuid import UUID

from app.core.config import settings
from app.db.models import SearchItem, SearchItemProduct, SearchRun
from app.db.session import SessionLocal
from ozon_parser.fetch import OzonFetchError
from ozon_parser.search import (
    OzonSearchError,
    OzonSearchItem,
    OzonSearchResult,
    fetch_search_browser,
)

LOGGER = logging.getLogger(__name__)

_SEARCH_LOCK = threading.Lock()


def build_search_options(
    *,
    source: str,
    cdp_url: str | None,
    timeout: float,
    challenge_timeout: float,
    limit: int,
    parse_products: bool,
    headless: bool,
) -> dict:
    options: dict = {
        "timeout": timeout,
        "challenge_timeout": challenge_timeout,
        "limit": limit,
        "parse_products": parse_products,
    }
    if source == "cdp":
        options["cdp_url"] = cdp_url or settings.cdp_url
    if source == "browser":
        options["headless"] = headless
    return options


def _parse_search(run: SearchRun) -> OzonSearchResult:
    options = run.options or {}
    timeout = float(options.get("timeout", settings.default_timeout))
    challenge_timeout = float(
        options.get("challenge_timeout", settings.default_challenge_timeout)
    )
    limit = int(options.get("limit", 20))
    parse_products = bool(options.get("parse_products", True))

    if run.source == "cdp":
        return fetch_search_browser(
            run.search_url,
            cdp_url=str(options.get("cdp_url") or settings.cdp_url),
            timeout=timeout,
            challenge_timeout=challenge_timeout,
            limit=limit,
            include_products=parse_products,
            headless=False,
        )
    if run.source == "browser":
        return fetch_search_browser(
            run.search_url,
            headless=bool(options.get("headless", False)),
            timeout=timeout,
            challenge_timeout=challenge_timeout,
            limit=limit,
            include_products=parse_products,
        )
    raise ValueError(f"Неизвестный источник поиска: {run.source}")


def _product_details(item: OzonSearchItem) -> SearchItemProduct | None:
    if item.product is None and not item.product_error:
        return None

    parsed_at = datetime.now(timezone.utc)
    if item.product is None:
        return SearchItemProduct(
            status="failed",
            name=item.name,
            sku=item.sku,
            price=item.price,
            currency=item.currency,
            error=item.product_error,
            duration_ms=item.product_duration_ms,
            parsed_at=parsed_at,
        )

    product = item.product
    return SearchItemProduct(
        status="success",
        name=product.name,
        description=product.description,
        sku=product.sku or item.sku,
        price=product.price,
        card_price=product.card_price,
        original_price=product.original_price,
        currency=product.currency or item.currency,
        in_stock=product.in_stock,
        seller=product.seller,
        brand=product.brand,
        rating=product.rating,
        review_count=product.review_count,
        image_url=product.image_urls[0] if product.image_urls else item.image_url,
        characteristics=product.characteristics or {},
        data=product.to_dict(),
        duration_ms=item.product_duration_ms,
        parsed_at=parsed_at,
    )


def _apply_result(run: SearchRun, result: OzonSearchResult) -> None:
    run.title = result.title
    run.query = result.query or run.query
    run.items_count = len(result.items)
    run.items.clear()
    for item in result.items:
        search_item = SearchItem(
            position=item.position,
            sku=item.sku,
            product_url=item.product_url,
            name=item.name,
            price=item.price,
            original_price=item.original_price,
            currency=item.currency,
            discount=item.discount,
            rating=item.rating,
            review_count=item.review_count,
            image_url=item.image_url,
            raw=item.to_dict(),
        )
        details = _product_details(item)
        if details is not None:
            search_item.product = details
        run.items.append(search_item)


def run_search(run_id: str | UUID) -> None:
    with _SEARCH_LOCK:
        session = SessionLocal()
        try:
            run = session.get(SearchRun, UUID(str(run_id)))
            if run is None or run.status != "queued":
                return

            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            run.error = None
            session.commit()

            started = time.perf_counter()
            try:
                result = _parse_search(run)
            except (OzonSearchError, OzonFetchError) as exc:
                _mark_failed(session, run, str(exc), started)
                LOGGER.warning("Search %s failed: %s", run.id, exc)
                return
            except Exception as exc:  # noqa: BLE001 - persist unexpected failures
                message = f"Внутренняя ошибка: {type(exc).__name__}: {exc}"
                _mark_failed(session, run, message, started)
                LOGGER.exception("Search %s crashed", run.id)
                return

            _apply_result(run, result)
            run.status = "success"
            run.finished_at = datetime.now(timezone.utc)
            run.duration_ms = int((time.perf_counter() - started) * 1000)
            session.commit()
            LOGGER.info(
                "Search %s finished in %s ms (%s items)",
                run.id,
                run.duration_ms,
                run.items_count,
            )
        finally:
            session.close()


def _mark_failed(session, run: SearchRun, message: str, started: float) -> None:
    run.status = "failed"
    run.finished_at = datetime.now(timezone.utc)
    run.duration_ms = int((time.perf_counter() - started) * 1000)
    run.error = message
    session.commit()

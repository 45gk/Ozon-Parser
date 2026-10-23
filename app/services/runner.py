from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from uuid import UUID

from app.core.config import settings
from app.db.models import ParseRun
from app.db.session import SessionLocal
from ozon_parser.api import fetch_product_api
from ozon_parser.browser import fetch_product_browser
from ozon_parser.fetch import OzonFetchError, fetch_product
from ozon_parser.parser import OzonProduct, OzonProductParseError

LOGGER = logging.getLogger(__name__)

# Ozon does not like parallel requests, and CDP is easier to drive one tab at a
# time. The web app is intentionally single-worker; this lock also protects
# against accidental concurrent runs in development.
_PARSE_LOCK = threading.Lock()


def build_options(
    *,
    source: str,
    cdp_url: str | None,
    timeout: float,
    challenge_timeout: float,
    headless: bool,
) -> dict:
    options: dict = {
        "timeout": timeout,
        "challenge_timeout": challenge_timeout,
    }
    if source == "cdp":
        options["cdp_url"] = cdp_url or settings.cdp_url
    if source == "browser":
        options["headless"] = headless
    return options


def _parse_product(run: ParseRun) -> OzonProduct:
    options = run.options or {}
    timeout = float(options.get("timeout", settings.default_timeout))
    challenge_timeout = float(
        options.get("challenge_timeout", settings.default_challenge_timeout)
    )

    if run.source == "cdp":
        return fetch_product_browser(
            run.product_url,
            cdp_url=str(options.get("cdp_url") or settings.cdp_url),
            timeout=timeout,
            challenge_timeout=challenge_timeout,
            headless=False,
        )
    if run.source == "browser":
        return fetch_product_browser(
            run.product_url,
            headless=bool(options.get("headless", False)),
            timeout=timeout,
            challenge_timeout=challenge_timeout,
        )
    if run.source == "api":
        return fetch_product_api(
            run.product_url,
            timeout=timeout,
            cookie=settings.ozon_cookie,
        )
    if run.source == "html":
        return fetch_product(run.product_url, timeout=timeout)

    raise ValueError(f"Неизвестный источник: {run.source}")


def _apply_product(run: ParseRun, product: OzonProduct) -> None:
    data = product.to_dict()
    run.product = data
    run.name = product.name
    run.sku = product.sku
    run.price = product.price
    run.currency = product.currency
    run.rating = product.rating
    run.review_count = product.review_count
    run.in_stock = product.in_stock
    run.seller = product.seller
    run.image_url = product.image_urls[0] if product.image_urls else None
    run.error = None


def run_parse(run_id: str | UUID) -> None:
    """Execute a queued parse and persist its result.

    Runs in a worker thread (FastAPI BackgroundTasks). Opens its own session
    because the request-scoped session is already closed by the time the task
    starts.
    """
    with _PARSE_LOCK:
        session = SessionLocal()
        try:
            run = session.get(ParseRun, UUID(str(run_id)))
            if run is None or run.status != "queued":
                return

            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            run.error = None
            session.commit()

            started = time.perf_counter()
            try:
                product = _parse_product(run)
            except (OzonFetchError, OzonProductParseError) as exc:
                _mark_failed(session, run, str(exc), started)
                LOGGER.warning("Parse %s failed: %s", run.id, exc)
                return
            except Exception as exc:  # noqa: BLE001 - persist unexpected failures
                message = f"Внутренняя ошибка: {type(exc).__name__}: {exc}"
                _mark_failed(session, run, message, started)
                LOGGER.exception("Parse %s crashed", run.id)
                return

            _apply_product(run, product)
            run.status = "success"
            run.finished_at = datetime.now(timezone.utc)
            run.duration_ms = int((time.perf_counter() - started) * 1000)
            session.commit()
            LOGGER.info("Parse %s finished in %s ms", run.id, run.duration_ms)
        finally:
            session.close()


def _mark_failed(session, run: ParseRun, message: str, started: float) -> None:
    run.status = "failed"
    run.finished_at = datetime.now(timezone.utc)
    run.duration_ms = int((time.perf_counter() - started) * 1000)
    run.error = message
    session.commit()

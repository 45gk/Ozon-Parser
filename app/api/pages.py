from __future__ import annotations

import json
from math import ceil
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_database
from app.repositories.runs import RunRepository
from app.schemas import RunCreate
from app.services.runner import build_options, run_parse
from app.templating import templates

router = APIRouter()

VALID_STATUSES = {"queued", "running", "success", "failed"}
VALID_SOURCES = {"cdp", "browser", "api", "html"}


def _first_error(exc: ValidationError) -> str:
    error = exc.errors()[0] if exc.errors() else {}
    message = str(error.get("msg", "Некорректные данные"))
    return message.removeprefix("Value error, ")


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    db: Session = Depends(get_database),
    status: str | None = None,
    source: str | None = None,
    q: str | None = None,
    page: int = 1,
    error: str | None = None,
    url: str | None = None,
) -> HTMLResponse:
    status = status if status in VALID_STATUSES else None
    source = source if source in VALID_SOURCES else None
    page = max(1, page)
    page_size = max(1, settings.page_size)

    repository = RunRepository(db)
    runs, total = repository.list_runs(
        status=status,
        source=source,
        query=q,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    pages = max(1, ceil(total / page_size))
    if page > pages and total:
        page = pages
        runs, total = repository.list_runs(
            status=status,
            source=source,
            query=q,
            limit=page_size,
            offset=(page - 1) * page_size,
        )

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "runs": runs,
            "total": total,
            "stats": repository.stats(),
            "filters": {
                "status": status or "",
                "source": source or "",
                "q": q or "",
            },
            "page": page,
            "pages": pages,
            "page_size": page_size,
            "error": error,
            "prefill_url": url or "",
            "cdp_url": settings.cdp_url,
            "default_timeout": settings.default_timeout,
            "default_challenge_timeout": settings.default_challenge_timeout,
        },
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(
    request: Request,
    run_id: str,
    db: Session = Depends(get_database),
) -> HTMLResponse:
    run = RunRepository(db).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Парсинг не найден")

    product = run.product or {}
    product_json = json.dumps(product, ensure_ascii=False, indent=2)
    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {
            "run": run,
            "product": product,
            "product_json": product_json,
            "images": product.get("image_urls") or [],
            "characteristics": product.get("characteristics") or {},
            "options": run.options or {},
        },
    )


@router.post("/runs")
def create_run_form(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_database),
    url: str = Form(...),
    source: str = Form("cdp"),
    cdp_url: str = Form(""),
    timeout: float = Form(settings.default_timeout),
    challenge_timeout: float = Form(settings.default_challenge_timeout),
    headless: str | None = Form(None),
) -> RedirectResponse:
    try:
        payload = RunCreate(
            url=url,
            source=source,
            cdp_url=cdp_url or None,
            timeout=timeout,
            challenge_timeout=challenge_timeout,
            headless=headless in {"on", "true", "1"},
        )
    except ValidationError as exc:
        query = urlencode(
            {
                "error": _first_error(exc),
                "url": url,
                "source": source,
            }
        )
        return RedirectResponse(f"/?{query}", status_code=303)

    options = build_options(
        source=payload.source,
        cdp_url=payload.cdp_url,
        timeout=payload.timeout,
        challenge_timeout=payload.challenge_timeout,
        headless=payload.headless,
    )
    run = RunRepository(db).create(
        product_url=payload.url,
        source=payload.source,
        options=options,
    )
    background_tasks.add_task(run_parse, run.id)
    return RedirectResponse(f"/runs/{run.id}", status_code=303)

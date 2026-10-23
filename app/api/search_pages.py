from __future__ import annotations

from math import ceil
from urllib.parse import parse_qs, urlencode, urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_database
from app.repositories.searches import SearchRepository
from app.search_schemas import SearchCreate
from app.services.search_runner import build_search_options, run_search
from app.templating import templates

router = APIRouter()

VALID_STATUSES = {"queued", "running", "success", "failed"}
VALID_SOURCES = {"cdp", "browser"}


def _first_error(exc: ValidationError) -> str:
    error = exc.errors()[0] if exc.errors() else {}
    message = str(error.get("msg", "Некорректные данные"))
    return message.removeprefix("Value error, ")


def _query_from_url(search_url: str) -> str | None:
    values = parse_qs(urlparse(search_url).query).get("text")
    if not values:
        return None
    query = values[0].strip()
    return query or None


@router.get("/searches", response_class=HTMLResponse)
def search_index(
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
    repository = SearchRepository(db)
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
        "search_index.html",
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
            "default_limit": 20,
        },
    )


@router.get("/searches/{run_id}", response_class=HTMLResponse)
def search_detail(
    request: Request,
    run_id: str,
    db: Session = Depends(get_database),
) -> HTMLResponse:
    run = SearchRepository(db).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Поиск не найден")
    return templates.TemplateResponse(
        request,
        "search_detail.html",
        {
            "run": run,
            "items": run.items,
            "options": run.options or {},
        },
    )


@router.post("/searches")
def create_search_form(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_database),
    url: str = Form(...),
    source: str = Form("cdp"),
    cdp_url: str = Form(""),
    timeout: float = Form(settings.default_timeout),
    challenge_timeout: float = Form(settings.default_challenge_timeout),
    limit: int = Form(20),
    headless: str | None = Form(None),
) -> RedirectResponse:
    try:
        payload = SearchCreate(
            url=url,
            source=source,
            cdp_url=cdp_url or None,
            timeout=timeout,
            challenge_timeout=challenge_timeout,
            limit=limit,
            headless=headless in {"on", "true", "1"},
        )
    except ValidationError as exc:
        query = urlencode({"error": _first_error(exc), "url": url, "source": source})
        return RedirectResponse(f"/searches?{query}", status_code=303)

    options = build_search_options(
        source=payload.source,
        cdp_url=payload.cdp_url,
        timeout=payload.timeout,
        challenge_timeout=payload.challenge_timeout,
        limit=payload.limit,
        headless=payload.headless,
    )
    run = SearchRepository(db).create(
        search_url=payload.url,
        query=_query_from_url(payload.url),
        source=payload.source,
        options=options,
    )
    background_tasks.add_task(run_search, run.id)
    return RedirectResponse(f"/searches/{run.id}", status_code=303)

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.search_serializers import search_run_to_detail, search_run_to_summary
from app.db.session import get_database
from app.repositories.searches import SearchRepository
from app.search_schemas import (
    SearchCreate,
    SearchCreated,
    SearchList,
    SearchRunDetail,
    SearchStats,
)
from app.services.search_runner import build_search_options, run_search
from ozon_parser.search import extract_search_query

router = APIRouter(prefix="/api/searches", tags=["searches"])

VALID_STATUSES = {"queued", "running", "success", "failed"}
VALID_SOURCES = {"cdp", "browser"}


@router.post("", response_model=SearchCreated, status_code=status.HTTP_202_ACCEPTED)
def create_search(
    payload: SearchCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_database),
) -> SearchCreated:
    options = build_search_options(
        source=payload.source,
        cdp_url=payload.cdp_url,
        timeout=payload.timeout,
        challenge_timeout=payload.challenge_timeout,
        limit=payload.limit,
        parse_products=payload.parse_products,
        headless=payload.headless,
    )
    run = SearchRepository(db).create(
        search_url=payload.url,
        query=extract_search_query(payload.url),
        source=payload.source,
        options=options,
    )
    background_tasks.add_task(run_search, run.id)
    return SearchCreated(id=str(run.id), status=run.status)


@router.get("", response_model=SearchList)
def list_searches(
    db: Session = Depends(get_database),
    status_value: str | None = Query(default=None, alias="status"),
    source: str | None = None,
    q: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> SearchList:
    if status_value and status_value not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail="Неизвестный статус")
    if source and source not in VALID_SOURCES:
        raise HTTPException(status_code=422, detail="Неизвестный источник")

    runs, total = SearchRepository(db).list_runs(
        status=status_value,
        source=source,
        query=q,
        limit=limit,
        offset=offset,
    )
    return SearchList(
        items=[search_run_to_summary(run) for run in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=SearchStats)
def search_stats(db: Session = Depends(get_database)) -> SearchStats:
    return SearchStats(**SearchRepository(db).stats())


@router.get("/{run_id}", response_model=SearchRunDetail)
def get_search(run_id: str, db: Session = Depends(get_database)) -> SearchRunDetail:
    run = SearchRepository(db).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Поиск не найден")
    return search_run_to_detail(run)

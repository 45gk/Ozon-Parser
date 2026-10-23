from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.serializers import run_to_detail, run_to_summary
from app.db.session import get_database
from app.repositories.runs import RunRepository
from app.schemas import RunCreate, RunCreated, RunDetail, RunList, Stats
from app.services.runner import build_options, run_parse

router = APIRouter(prefix="/api", tags=["runs"])

VALID_STATUSES = {"queued", "running", "success", "failed"}
VALID_SOURCES = {"cdp", "browser", "api", "html"}


@router.post("/runs", response_model=RunCreated, status_code=status.HTTP_202_ACCEPTED)
def create_run(
    payload: RunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_database),
) -> RunCreated:
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
    return RunCreated(id=str(run.id), status=run.status)


@router.get("/runs", response_model=RunList)
def list_runs(
    db: Session = Depends(get_database),
    status_value: str | None = Query(default=None, alias="status"),
    source: str | None = None,
    q: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> RunList:
    if status_value and status_value not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail="Неизвестный статус")
    if source and source not in VALID_SOURCES:
        raise HTTPException(status_code=422, detail="Неизвестный источник")

    runs, total = RunRepository(db).list_runs(
        status=status_value,
        source=source,
        query=q,
        limit=limit,
        offset=offset,
    )
    return RunList(
        items=[run_to_summary(run) for run in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str, db: Session = Depends(get_database)) -> RunDetail:
    run = RunRepository(db).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Парсинг не найден")
    return run_to_detail(run)


@router.get("/stats", response_model=Stats)
def get_stats(db: Session = Depends(get_database)) -> Stats:
    return Stats(**RunRepository(db).stats())

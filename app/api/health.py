from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_database

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_database)) -> dict:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="База данных недоступна") from exc
    return {
        "status": "ok",
        "database": "ok",
        "version": settings.app_version,
    }

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.models import ParseRun

connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_database() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)


def mark_stale_runs() -> int:
    """Mark jobs interrupted by a server restart as failed."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        result = session.execute(
            update(ParseRun)
            .where(ParseRun.status.in_(("queued", "running")))
            .values(
                status="failed",
                error="Парсинг прерван перезапуском сервера",
                finished_at=now,
            )
        )
        session.commit()
        return result.rowcount or 0

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import SearchRun


class SearchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        search_url: str,
        query: str | None,
        source: str,
        options: dict,
    ) -> SearchRun:
        run = SearchRun(
            search_url=search_url,
            query=query,
            source=source,
            status="queued",
            options=options,
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def get(self, run_id: str | UUID) -> SearchRun | None:
        try:
            identifier = run_id if isinstance(run_id, UUID) else UUID(str(run_id))
        except (ValueError, TypeError):
            return None
        return self.session.scalar(
            select(SearchRun)
            .options(selectinload(SearchRun.items))
            .where(SearchRun.id == identifier)
        )

    def list_runs(
        self,
        *,
        status: str | None = None,
        source: str | None = None,
        query: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SearchRun], int]:
        conditions = []
        if status:
            conditions.append(SearchRun.status == status)
        if source:
            conditions.append(SearchRun.source == source)
        if query:
            pattern = f"%{query.strip()}%"
            conditions.append(
                or_(
                    SearchRun.search_url.ilike(pattern),
                    SearchRun.query.ilike(pattern),
                    SearchRun.title.ilike(pattern),
                )
            )

        statement = select(SearchRun)
        count_statement = select(func.count()).select_from(SearchRun)
        if conditions:
            statement = statement.where(*conditions)
            count_statement = count_statement.where(*conditions)

        statement = (
            statement.order_by(SearchRun.created_at.desc()).limit(limit).offset(offset)
        )
        runs = list(self.session.scalars(statement).all())
        total = self.session.scalar(count_statement) or 0
        return runs, total

    def stats(self) -> dict:
        total = self.session.scalar(select(func.count()).select_from(SearchRun)) or 0
        by_status = dict(
            self.session.execute(
                select(SearchRun.status, func.count(SearchRun.id)).group_by(
                    SearchRun.status
                )
            ).all()
        )
        success = by_status.get("success", 0)
        failed = by_status.get("failed", 0)
        active = by_status.get("queued", 0) + by_status.get("running", 0)
        unique_queries = (
            self.session.scalar(
                select(func.count(func.distinct(SearchRun.query))).where(
                    SearchRun.query.is_not(None)
                )
            )
            or 0
        )
        total_items = (
            self.session.scalar(
                select(func.coalesce(func.sum(SearchRun.items_count), 0))
            )
            or 0
        )
        avg_duration = self.session.scalar(
            select(func.avg(SearchRun.duration_ms)).where(SearchRun.status == "success")
        )
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "active": active,
            "unique_queries": unique_queries,
            "total_items": int(total_items),
            "avg_duration_ms": int(avg_duration) if avg_duration is not None else None,
            "success_rate": round(success / total * 100, 1) if total else 0.0,
        }

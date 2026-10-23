from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import ParseRun


class RunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        product_url: str,
        source: str,
        options: dict,
    ) -> ParseRun:
        run = ParseRun(
            product_url=product_url,
            source=source,
            status="queued",
            options=options,
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def get(self, run_id: str | UUID) -> ParseRun | None:
        try:
            identifier = run_id if isinstance(run_id, UUID) else UUID(str(run_id))
        except (ValueError, TypeError):
            return None
        return self.session.get(ParseRun, identifier)

    def list_runs(
        self,
        *,
        status: str | None = None,
        source: str | None = None,
        query: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ParseRun], int]:
        conditions = []
        if status:
            conditions.append(ParseRun.status == status)
        if source:
            conditions.append(ParseRun.source == source)
        if query:
            pattern = f"%{query.strip()}%"
            conditions.append(
                or_(
                    ParseRun.product_url.ilike(pattern),
                    ParseRun.name.ilike(pattern),
                    ParseRun.sku.ilike(pattern),
                    ParseRun.seller.ilike(pattern),
                )
            )

        statement = select(ParseRun)
        count_statement = select(func.count()).select_from(ParseRun)
        if conditions:
            statement = statement.where(*conditions)
            count_statement = count_statement.where(*conditions)

        statement = (
            statement.order_by(ParseRun.created_at.desc()).limit(limit).offset(offset)
        )
        runs = list(self.session.scalars(statement).all())
        total = self.session.scalar(count_statement) or 0
        return runs, total

    def stats(self) -> dict:
        total = self.session.scalar(select(func.count()).select_from(ParseRun)) or 0
        by_status = dict(
            self.session.execute(
                select(ParseRun.status, func.count(ParseRun.id)).group_by(
                    ParseRun.status
                )
            ).all()
        )
        success = by_status.get("success", 0)
        failed = by_status.get("failed", 0)
        active = by_status.get("queued", 0) + by_status.get("running", 0)
        unique_products = (
            self.session.scalar(
                select(func.count(func.distinct(ParseRun.sku))).where(
                    ParseRun.sku.is_not(None)
                )
            )
            or 0
        )
        avg_duration = self.session.scalar(
            select(func.avg(ParseRun.duration_ms)).where(ParseRun.status == "success")
        )
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "active": active,
            "unique_products": unique_products,
            "avg_duration_ms": int(avg_duration) if avg_duration is not None else None,
            "success_rate": round(success / total * 100, 1) if total else 0.0,
        }

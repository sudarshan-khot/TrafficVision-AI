"""
Analytics aggregation queries.

Requirements: 5.1, 5.4
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Violation


async def compute_analytics(
    db: AsyncSession,
    start_date: datetime,
    end_date: datetime,
) -> dict:
    """
    Aggregate violation counts grouped by type and by date.

    Returns
    -------
    dict
        ``{"by_type": {...}, "by_date": [...], "total": int}``
    """
    by_type_result = await db.execute(
        select(Violation.violation_type, func.count())
        .where(Violation.created_at >= start_date)
        .where(Violation.created_at <= end_date)
        .group_by(Violation.violation_type)
    )
    by_type = {row[0]: int(row[1]) for row in by_type_result.all()}

    by_date_result = await db.execute(
        select(
            func.date(Violation.created_at).label("date"),
            func.count(),
        )
        .where(Violation.created_at >= start_date)
        .where(Violation.created_at <= end_date)
        .group_by(func.date(Violation.created_at))
        .order_by(func.date(Violation.created_at))
    )
    by_date = [
        {"date": str(row[0]), "count": int(row[1])}
        for row in by_date_result.all()
    ]

    total = sum(by_type.values())
    return {"by_type": by_type, "by_date": by_date, "total": total}

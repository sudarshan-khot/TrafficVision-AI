"""
Analytics cache read/write helpers.

Requirements: 5.2, 5.3, 5.5
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AnalyticsCache

_CACHE_TTL = timedelta(minutes=5)


async def get_cached(
    db: AsyncSession,
    window_start: datetime,
    window_end: datetime,
) -> dict | None:
    """
    Return cached analytics for the window when all rows are fresh.

    Returns ``None`` when the cache is absent or stale.
    """
    result = await db.execute(
        select(AnalyticsCache)
        .where(AnalyticsCache.window_start == window_start)
        .where(AnalyticsCache.window_end == window_end)
    )
    rows = list(result.scalars().all())
    if not rows:
        return None

    now = datetime.now(timezone.utc)
    for row in rows:
        updated_at = row.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if now - updated_at > _CACHE_TTL:
            return None

    by_type = {row.violation_type: row.count for row in rows}
    total = sum(by_type.values())
    by_date = rows[0].by_date or []
    return {"by_type": by_type, "by_date": by_date, "total": total}


async def set_cache(
    db: AsyncSession,
    window_start: datetime,
    window_end: datetime,
    by_type: dict[str, int],
    by_date: list[dict],
) -> None:
    """Upsert per-type cache rows for the given window."""
    now = datetime.now(timezone.utc)

    for violation_type, count in by_type.items():
        result = await db.execute(
            select(AnalyticsCache)
            .where(AnalyticsCache.window_start == window_start)
            .where(AnalyticsCache.window_end == window_end)
            .where(AnalyticsCache.violation_type == violation_type)
        )
        row = result.scalar_one_or_none()
        if row:
            row.count = count
            row.by_date = by_date
            row.updated_at = now
        else:
            db.add(
                AnalyticsCache(
                    window_start=window_start,
                    window_end=window_end,
                    violation_type=violation_type,
                    count=count,
                    by_date=by_date,
                    updated_at=now,
                )
            )

    await db.flush()

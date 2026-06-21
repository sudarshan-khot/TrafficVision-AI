"""
GET /analytics route handler.

Requirements: 5.1–5.5
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.aggregator import compute_analytics
from app.analytics.cache import get_cached, set_cache
from app.database.session import get_db

router = APIRouter()


@router.get("/analytics")
async def get_analytics(
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    window_end = end_date or now
    window_start = start_date or (now - timedelta(days=30))

    cached = await get_cached(db, window_start, window_end)
    if cached is not None:
        return {
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "by_type": cached["by_type"],
            "by_date": cached["by_date"],
            "total": cached["total"],
            "cached": True,
        }

    result = await compute_analytics(db, window_start, window_end)
    await set_cache(db, window_start, window_end, result["by_type"], result["by_date"])
    await db.commit()

    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "by_type": result["by_type"],
        "by_date": result["by_date"],
        "total": result["total"],
        "cached": False,
    }

"""
GET /health route handler.

Requirements: 6.1–6.3
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies import get_storage_service
from app.services.storage_service import StorageService

router = APIRouter()


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
):
    timestamp = datetime.now(timezone.utc).isoformat()
    db_status = "ok"
    db_error: str | None = None
    storage_status = "ok"
    storage_error: str | None = None

    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db_status = "unreachable"
        db_error = str(exc)

    try:
        if storage is None:
            storage_status = "unreachable"
            storage_error = "StorageService was not initialised at startup. Check server logs for the root cause."
        else:
            exists = await _bucket_exists(storage)
            if not exists:
                storage_status = "unreachable"
                storage_error = f"Bucket '{storage._bucket}' does not exist or is inaccessible."  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        storage_status = "unreachable"
        storage_error = str(exc)

    overall = "healthy" if db_status == "ok" and storage_status == "ok" else "degraded"
    status_code = status.HTTP_200_OK if overall == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE

    body: dict = {
        "status": overall,
        "database": db_status,
        "storage": storage_status,
        "timestamp": timestamp,
    }
    if db_error:
        body["database_error"] = db_error
    if storage_error:
        body["storage_error"] = storage_error

    return JSONResponse(status_code=status_code, content=body)


async def _bucket_exists(storage: StorageService) -> bool:
    import asyncio

    return await asyncio.to_thread(storage._client.bucket_exists, storage._bucket)  # noqa: SLF001

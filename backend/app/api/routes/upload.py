"""
POST /upload-image route handler.

Requirements: 1.1–1.5
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies import get_storage_service
from app.services.image_service import (
    FileTooLargeError,
    ImageService,
    UnsupportedMediaTypeError,
)
from app.services.storage_service import StorageService, StorageUnavailableError

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    storage: StorageService = Depends(get_storage_service),
    db: AsyncSession = Depends(get_db),
):
    if storage is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "Storage service unavailable",
                "reason": "Storage backend failed to initialise at startup. Check server logs for the root cause.",
            },
        )

    image_service = ImageService(storage)
    try:
        await image_service.validate_upload(file)
    except FileTooLargeError as exc:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": str(exc)},
        )
    except UnsupportedMediaTypeError as exc:
        return JSONResponse(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            content={"detail": str(exc)},
        )

    image_id = str(uuid.uuid4())
    file_bytes = await file.read()
    content_type = (file.content_type or "image/jpeg").lower()

    try:
        object_path = await image_service.store_original(
            image_id=image_id,
            file_bytes=file_bytes,
            content_type=content_type,
        )
    except StorageUnavailableError as exc:
        logger.error("Storage unavailable during upload (image_id=%s): %s", image_id, exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "Storage service unavailable",
                "reason": str(exc),
            },
        )

    _ = db  # reserved for future metadata persistence
    return {
        "image_id": image_id,
        "object_path": object_path,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }

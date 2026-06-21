"""
POST /analyze route handler.

Requirements: 2.1–2.11
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies import (
    get_detection_service,
    get_evidence_generator,
    get_evidence_uploader,
    get_ocr_pipeline,
    get_storage_service,
    get_violation_engine,
)
from app.services.analysis_service import analysis_service
from app.services.storage_service import StorageService, StorageUnavailableError

logger = logging.getLogger(__name__)
router = APIRouter()


class AnalyzeRequest(BaseModel):
    image_id: str
    object_path: str | None = None


@router.post("/analyze")
async def analyze_image(
    body: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    detector=Depends(get_detection_service),
    ocr=Depends(get_ocr_pipeline),
    violation_engine=Depends(get_violation_engine),
    evidence_gen=Depends(get_evidence_generator),
    evidence_uploader=Depends(get_evidence_uploader),
):
    if storage is None or detector is None or ocr is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Analysis services unavailable"},
        )

    resolved_path = body.object_path
    try:
        if resolved_path:
            await storage.get_object(resolved_path)
        else:
            for ext in ("jpg", "png"):
                candidate = f"original/{body.image_id}.{ext}"
                try:
                    await storage.get_object(candidate)
                    resolved_path = candidate
                    break
                except Exception:  # noqa: BLE001
                    continue
            if not resolved_path:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content={"detail": "Image not found"},
                )
    except StorageUnavailableError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Storage service unavailable"},
        )
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Image not found"},
        )

    try:
        result = await analysis_service.run_analysis(
            image_id=body.image_id,
            db=db,
            storage=storage,
            detector=detector,
            ocr=ocr,
            violation_engine=violation_engine,
            evidence_gen=evidence_gen,
            evidence_uploader=evidence_uploader,
            original_object_path=resolved_path,
        )
    except FileNotFoundError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Image not found"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Detection failed for image %s", body.image_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Detection failed"},
        )

    return result

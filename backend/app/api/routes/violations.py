"""
GET /violations route handlers.

Requirements: 4.1–4.5
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Vehicle
from app.database.session import get_db
from app.dependencies import get_storage_service
from app.services.storage_service import StorageService
from app.services.violation_service import ViolationService

router = APIRouter()


@router.get("/violations")
async def list_violations(
    violation_type: str | None = None,
    plate_number: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    service = ViolationService(db)
    results, total_count = await service.list_violations(
        violation_type=violation_type,
        plate_number=plate_number,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )

    return {
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "results": [
            {
                "id": row.id,
                "image_id": row.image_id,
                "vehicle_id": row.vehicle_id,
                "violation_type": row.violation_type,
                "confidence": row.confidence,
                "bounding_box": row.bounding_box,
                "plate_number": row.plate_number,
                "annotated_image_path": row.annotated_image_path,
                "created_at": row.created_at.isoformat(),
            }
            for row in results
        ],
    }


@router.get("/violations/{violation_id}")
async def get_violation(
    violation_id: str,
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
):
    service = ViolationService(db)
    violation = await service.get_violation_by_id(violation_id)
    if violation is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Violation not found"},
        )

    vehicle_data = None
    if violation.vehicle is not None:
        vehicle_data = {
            "id": violation.vehicle.id,
            "vehicle_class": violation.vehicle.vehicle_class,
            "bounding_box": violation.vehicle.bounding_box,
            "plate_number": violation.vehicle.plate_number,
        }

    annotated_image_url = None
    if violation.annotated_image_path and storage is not None:
        annotated_image_url = await storage.get_presigned_url(
            violation.annotated_image_path,
            expiry_seconds=3600,
        )

    original_image_url = None
    if storage is not None:
        for ext in ("jpg", "png"):
            candidate = f"original/{violation.image_id}.{ext}"
            try:
                await asyncio.to_thread(storage._client.stat_object, storage._bucket, candidate)
                original_image_url = await storage.get_presigned_url(
                    candidate,
                    expiry_seconds=3600,
                )
                break
            except Exception:
                continue

    vehicles_result = await db.execute(
        select(Vehicle).where(Vehicle.image_id == violation.image_id)
    )
    all_vehicles = [
        {
            "id": v.id,
            "vehicle_class": v.vehicle_class,
            "bounding_box": v.bounding_box,
            "plate_number": v.plate_number,
        }
        for v in vehicles_result.scalars().all()
    ]

    return {
        "id": violation.id,
        "image_id": violation.image_id,
        "vehicle": vehicle_data,
        "violation_type": violation.violation_type,
        "confidence": violation.confidence,
        "bounding_box": violation.bounding_box,
        "plate_number": violation.plate_number,
        "annotated_image_url": annotated_image_url,
        "original_image_url": original_image_url,
        "all_vehicles": all_vehicles,
        "created_at": violation.created_at.isoformat(),
    }

"""
Violation and vehicle persistence service.

Requirements: 2.4, 2.6, 3.4, 4.1, 4.2, 4.4, 4.5
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import Vehicle, Violation


class ViolationService:
    """Async CRUD operations for violations and vehicles."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_vehicle(
        self,
        image_id: str,
        vehicle_class: str,
        bounding_box: dict,
        plate_number: str | None = None,
        vehicle_id: str | None = None,
    ) -> Vehicle:
        vehicle = Vehicle(
            id=vehicle_id,
            image_id=image_id,
            vehicle_class=vehicle_class,
            bounding_box=bounding_box,
            plate_number=plate_number,
        )
        self._db.add(vehicle)
        await self._db.flush()
        return vehicle

    async def create_violation(
        self,
        image_id: str,
        violation_type: str,
        confidence: float,
        bounding_box: dict,
        vehicle_id: str | None = None,
        plate_number: str | None = None,
        annotated_image_path: str | None = None,
    ) -> Violation:
        violation = Violation(
            image_id=image_id,
            vehicle_id=vehicle_id,
            violation_type=violation_type,
            confidence=confidence,
            bounding_box=bounding_box,
            plate_number=plate_number,
            annotated_image_path=annotated_image_path,
        )
        self._db.add(violation)
        await self._db.flush()
        return violation

    async def get_violation_by_id(self, violation_id: str) -> Violation | None:
        result = await self._db.execute(
            select(Violation)
            .options(selectinload(Violation.vehicle))
            .where(Violation.id == violation_id)
        )
        return result.scalar_one_or_none()

    async def list_violations(
        self,
        violation_type: str | None = None,
        plate_number: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Violation], int]:
        query = select(Violation)
        count_query = select(func.count()).select_from(Violation)

        if violation_type:
            query = query.where(Violation.violation_type == violation_type)
            count_query = count_query.where(Violation.violation_type == violation_type)
        if plate_number:
            query = query.where(Violation.plate_number == plate_number)
            count_query = count_query.where(Violation.plate_number == plate_number)
        if start_date:
            query = query.where(Violation.created_at >= start_date)
            count_query = count_query.where(Violation.created_at >= start_date)
        if end_date:
            query = query.where(Violation.created_at <= end_date)
            count_query = count_query.where(Violation.created_at <= end_date)

        total_result = await self._db.execute(count_query)
        total_count = int(total_result.scalar_one())

        offset = max(0, (page - 1) * page_size)
        query = (
            query.order_by(Violation.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self._db.execute(query)
        return list(result.scalars().all()), total_count

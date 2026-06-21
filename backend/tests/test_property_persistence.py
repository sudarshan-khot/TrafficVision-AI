"""Property-based persistence tests (Properties 3-6, 8)."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.analytics.aggregator import compute_analytics
from app.database.models import Vehicle, Violation
from app.services.violation_service import ViolationService


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


async def _vehicle_count(session) -> int:
    result = await session.scalar(select(func.count()).select_from(Vehicle))
    return int(result or 0)


async def _violation_count(session) -> int:
    result = await session.scalar(select(func.count()).select_from(Violation))
    return int(result or 0)


@pytest.mark.parametrize("n", [0, 1, 3, 5])
def test_vehicle_persistence_count(db_engine, n: int):
    async def _test():
        from sqlalchemy.ext.asyncio import async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False)
        async with factory() as session:
            before = await _vehicle_count(session)
            service = ViolationService(session)
            for _ in range(n):
                await service.create_vehicle(
                    image_id="img-prop",
                    vehicle_class="motorcycle",
                    bounding_box={"x1": 0, "y1": 0, "x2": 10, "y2": 10},
                )
            await session.commit()
            after = await _vehicle_count(session)
            assert after - before == n

    _run(_test())


@pytest.mark.parametrize("n", [0, 1, 3, 5])
def test_violation_persistence_count(db_engine, n: int):
    async def _test():
        from sqlalchemy.ext.asyncio import async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False)
        async with factory() as session:
            before = await _violation_count(session)
            service = ViolationService(session)
            for _ in range(n):
                await service.create_violation(
                    image_id="img-prop",
                    violation_type="HELMET_NON_COMPLIANCE",
                    confidence=0.5,
                    bounding_box={"x1": 0, "y1": 0, "x2": 10, "y2": 10},
                )
            await session.commit()
            after = await _violation_count(session)
            assert after - before == n

    _run(_test())


@pytest.mark.asyncio
async def test_failed_insert_rollback(db_session):
    service = ViolationService(db_session)
    before = await _violation_count(db_session)
    try:
        await service.create_violation(
            image_id="img-prop",
            violation_type="HELMET_NON_COMPLIANCE",
            confidence=1.5,
            bounding_box={"x1": 0, "y1": 0, "x2": 10, "y2": 10},
        )
        await db_session.commit()
    except Exception:  # noqa: BLE001
        await db_session.rollback()
    after = await _violation_count(db_session)
    assert after == before


@pytest.mark.asyncio
async def test_pagination_envelope(db_session):
    service = ViolationService(db_session)
    now = datetime.now(timezone.utc)
    for i in range(7):
        db_session.add(
            Violation(
                id=str(uuid.uuid4()),
                image_id="a47ac10b-58cc-4372-a567-0e02b2c3d480",
                violation_type="HELMET_NON_COMPLIANCE",
                confidence=0.8,
                bounding_box={"x1": 0, "y1": 0, "x2": 1, "y2": 1},
                created_at=now - timedelta(hours=i),
            )
        )
    await db_session.commit()

    results, total = await service.list_violations(page=1, page_size=2)
    assert total == 7
    assert len(results) == 2
    timestamps = [r.created_at for r in results]
    assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.asyncio
async def test_analytics_consistency(db_session):
    now = datetime.now(timezone.utc)
    for i in range(3):
        db_session.add(
            Violation(
                id=f"a0000000-0000-4000-8000-00000000000{i}",
                image_id="a47ac10b-58cc-4372-a567-0e02b2c3d480",
                violation_type="HELMET_NON_COMPLIANCE",
                confidence=0.9,
                bounding_box={"x1": 0, "y1": 0, "x2": 1, "y2": 1},
                created_at=now,
            )
        )
    for i in range(2):
        db_session.add(
            Violation(
                id=f"b0000000-0000-4000-8000-00000000000{i}",
                image_id="a47ac10b-58cc-4372-a567-0e02b2c3d480",
                violation_type="TRIPLE_RIDING",
                confidence=0.8,
                bounding_box={"x1": 0, "y1": 0, "x2": 1, "y2": 1},
                created_at=now,
            )
        )
    await db_session.commit()

    start = now - timedelta(days=1)
    end = now + timedelta(days=1)
    result = await compute_analytics(db_session, start, end)
    assert sum(result["by_type"].values()) == result["total"]

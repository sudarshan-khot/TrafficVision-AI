"""
Shared pytest fixtures for TrafficVision AI backend tests.

Requirements: 15.1, 15.5
"""
from __future__ import annotations

import asyncio
import io
import os
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.database.models import Base, Vehicle, Violation
from app.main import create_app

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

TEST_DATABASE_URL = os.environ["DATABASE_URL"]


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_: JSONB, compiler: Any, **kw: Any) -> str:
    return "JSON"


def _run_async(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


@pytest.fixture()
def mock_storage() -> MagicMock:
    storage = MagicMock()
    storage.put_object = AsyncMock(return_value="original/test-id.jpg")
    storage.get_object = AsyncMock(return_value=_make_jpeg())
    storage.get_presigned_url = AsyncMock(return_value="https://minio.example.com/signed")
    storage.ensure_bucket = AsyncMock()
    storage._client = MagicMock()
    storage._client.bucket_exists = MagicMock(return_value=True)
    storage._bucket = "traffic-images"
    return storage


def _make_jpeg() -> bytes:
    img = Image.new("RGB", (64, 64), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def mock_detector():
    from app.detection.models import BoundingBox, DetectedObject, DetectionResult

    detector = MagicMock()

    def _detect(image_bytes: bytes, image_id: str) -> DetectionResult:
        moto = DetectedObject(
            id="f47ac10b-58cc-4372-a567-0e02b2c3d479",
            cls="motorcycle",
            confidence=0.9,
            bounding_box=BoundingBox(x1=10, y1=10, x2=100, y2=100),
            attributes={"rider_count": 1},
        )
        person = DetectedObject(
            id="a47ac10b-58cc-4372-a567-0e02b2c3d480",
            cls="person",
            confidence=0.85,
            bounding_box=BoundingBox(x1=20, y1=20, x2=60, y2=80),
            attributes={"helmet": False},
            associated_vehicle_id="f47ac10b-58cc-4372-a567-0e02b2c3d479",
        )
        return DetectionResult(
            image_id=image_id,
            objects=[moto, person],
            motorcycles=[moto],
        )

    detector.detect = MagicMock(side_effect=_detect)
    return detector


@pytest.fixture()
def mock_ocr():
    ocr = MagicMock()
    ocr.read_plate = MagicMock(return_value="MH12DE1433")
    ocr.read_plate_with_crop = MagicMock(return_value=("MH12DE1433", _make_jpeg()))
    return ocr


@pytest.fixture()
def sample_jpeg() -> bytes:
    return _make_jpeg()


@pytest.fixture()
def client(mock_storage, mock_detector, mock_ocr, db_engine) -> Generator[TestClient, None, None]:
    from app.database.session import get_db
    from app.dependencies import (
        get_detection_service,
        get_evidence_generator,
        get_evidence_uploader,
        get_ocr_pipeline,
        get_storage_service,
        get_violation_engine,
    )
    from app.evidence.generator import EvidenceGenerator
    from app.evidence.uploader import EvidenceUploader
    from app.violation_engine.engine import ViolationEngine

    engine = db_engine

    async def init_db():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    _run_async(init_db())
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app = create_app(testing=True)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_service] = lambda: mock_storage
    app.dependency_overrides[get_detection_service] = lambda: mock_detector
    app.dependency_overrides[get_ocr_pipeline] = lambda: mock_ocr
    app.dependency_overrides[get_violation_engine] = lambda: ViolationEngine()
    app.dependency_overrides[get_evidence_generator] = lambda: EvidenceGenerator()
    app.dependency_overrides[get_evidence_uploader] = lambda: EvidenceUploader(mock_storage)

    with TestClient(app, raise_server_exceptions=False) as test_client:
        test_client.app.state.storage_service = mock_storage
        test_client.app.state.detection_service = mock_detector
        test_client.app.state.ocr_pipeline = mock_ocr
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture()
def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async def init_db():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    _run_async(init_db())
    yield engine
    _run_async(engine.dispose())


@pytest_asyncio.fixture()
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture()
async def seed_violations(db_session: AsyncSession) -> list[Violation]:
    now = datetime.now(timezone.utc)
    vehicle = Vehicle(
        id="f47ac10b-58cc-4372-a567-0e02b2c3d479",
        image_id="a47ac10b-58cc-4372-a567-0e02b2c3d480",
        vehicle_class="motorcycle",
        bounding_box={"x1": 0, "y1": 0, "x2": 10, "y2": 10},
        plate_number="MH12DE1433",
        created_at=now,
    )
    db_session.add(vehicle)
    violation_ids = [
        "b47ac10b-58cc-4372-a567-0e02b2c3d481",
        "c47ac10b-58cc-4372-a567-0e02b2c3d482",
        "d47ac10b-58cc-4372-a567-0e02b2c3d483",
        "e47ac10b-58cc-4372-a567-0e02b2c3d484",
        "f57ac10b-58cc-4372-a567-0e02b2c3d485",
    ]
    violations = []
    for vid in violation_ids:
        v = Violation(
            id=vid,
            image_id="a47ac10b-58cc-4372-a567-0e02b2c3d480",
            vehicle_id="f47ac10b-58cc-4372-a567-0e02b2c3d479",
            violation_type="HELMET_NON_COMPLIANCE",
            confidence=0.9,
            bounding_box={"x1": 0, "y1": 0, "x2": 10, "y2": 10},
            plate_number="MH12DE1433",
            created_at=now,
        )
        db_session.add(v)
        violations.append(v)
    await db_session.commit()
    return violations

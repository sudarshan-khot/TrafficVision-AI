"""
Application startup routines.

Called from ``main.py`` lifespan on boot.  Ensures infrastructure is ready
before serving requests.

Requirements: 7.1, 7.2, 7.3, 14.3
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI

from app.config import settings
from app.services.storage_service import (
    StorageService,
    MinioStorageBackend,
)

logger = logging.getLogger(__name__)


def validate_model_files(model_dir: str | None = None) -> None:
    """
    Verify required YOLO weight files (either ONNX or PyTorch) exist.

    Raises
    ------
    SystemExit
        With exit code 1 when required weight files are missing.
    """
    base = Path(model_dir or settings.MODEL_DIR)
    
    # Try to validate ONNX weights and name JSON mappings first (preferred in production)
    yolov8_onnx = "yolov8m.onnx"
    if not (base / yolov8_onnx).is_file():
        yolov8_onnx = "yolov8n.onnx"
        
    required_onnx = [yolov8_onnx, yolov8_onnx.replace(".onnx", ".names.json"), "yolo26n.onnx", "yolo26n.names.json"]
    
    has_onnx = all((base / name).is_file() for name in required_onnx)
    if has_onnx:
        logger.info("ONNX model and metadata files validated in %s", base.resolve())
        return

    # Fallback to PyTorch weights validation
    yolov8_pt = "yolov8m.pt"
    if not (base / yolov8_pt).is_file():
        yolov8_pt = "yolov8n.pt"
        
    required_pt = [yolov8_pt, "yolo26n.pt"]
    for name in required_pt:
        path = base / name
        if not path.is_file():
            msg = (
                f"Required model file not found (tried ONNX and PyTorch weights): {path.resolve()}\n"
                f"Place either ONNX weights ({required_onnx}) or PyTorch weights ({required_pt}) in the directory."
            )
            logger.error(msg)
            sys.exit(1)
    logger.info("PyTorch model weights validated in %s", base.resolve())


def run_migrations() -> None:
    """Apply Alembic migrations programmatically (``alembic upgrade head``)."""
    backend_root = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic migrations applied")


async def run_startup(app: FastAPI, *, skip_models: bool = False) -> None:
    """
    Run all startup checks and initialisation steps.

    Parameters
    ----------
    app:
        FastAPI application instance (services stored on ``app.state``).
    skip_models:
        When ``True``, skip ML model validation and loading (used in tests).
    """
    if settings.APP_ENV == "test":
        app.state.storage_service = None
        app.state.detection_service = None
        app.state.ocr_pipeline = None
        return

    retries = 5
    delay = 2
    for attempt in range(1, retries + 1):
        try:
            await asyncio.to_thread(run_migrations)
            break
        except Exception as exc:
            if attempt == retries:
                logger.error("Migration step failed after %d attempts: %s", retries, exc)
                raise
            logger.warning(
                "Migration attempt %d/%d failed (retrying in %ds): %s",
                attempt,
                retries,
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    try:
        backend_name = settings.STORAGE_BACKEND.lower()
        if backend_name == "supabase":
            if not settings.SUPABASE_PROJECT_REF:
                raise ValueError("STORAGE_BACKEND=supabase requires SUPABASE_PROJECT_REF to be set.")
            if not settings.SUPABASE_S3_ACCESS_KEY_ID or not settings.SUPABASE_S3_SECRET_ACCESS_KEY:
                raise ValueError(
                    "STORAGE_BACKEND=supabase requires SUPABASE_S3_ACCESS_KEY_ID and "
                    "SUPABASE_S3_SECRET_ACCESS_KEY to be set."
                )
            backend = MinioStorageBackend(
                endpoint=settings.supabase_s3_endpoint,
                access_key=settings.SUPABASE_S3_ACCESS_KEY_ID,
                secret_key=settings.SUPABASE_S3_SECRET_ACCESS_KEY,
                bucket=settings.SUPABASE_BUCKET,
                secure=True,  # Supabase always uses HTTPS
            )
            bucket_name = settings.SUPABASE_BUCKET
            logger.info(
                "Storage backend: Supabase S3 (endpoint: %s, bucket: %s)",
                settings.supabase_s3_endpoint,
                bucket_name,
            )
        else:
            backend = MinioStorageBackend(
                endpoint=settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                bucket=settings.MINIO_BUCKET,
                secure=settings.MINIO_SECURE,
                public_endpoint=settings.MINIO_PUBLIC_ENDPOINT,
            )
            bucket_name = settings.MINIO_BUCKET
            logger.info(
                "Storage backend: MinIO (endpoint: %s, bucket: %s)",
                settings.MINIO_ENDPOINT,
                bucket_name,
            )

        storage = StorageService(backend=backend, bucket=bucket_name)
        await storage.ensure_bucket()
        app.state.storage_service = storage
        logger.info("StorageService ready (backend=%s, bucket=%s)", backend_name, bucket_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("StorageService initialisation failed: %s", exc)
        app.state.storage_service = None

    if skip_models:
        app.state.detection_service = None
        app.state.ocr_pipeline = None
        return

    validate_model_files()

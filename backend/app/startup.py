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
    # Convert asyncpg URL back to a sync psycopg2-compatible URL for Alembic
    sync_url = settings.DATABASE_URL
    sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql://")
    # asyncpg uses ssl=require; psycopg2 uses sslmode=require
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    parsed = urlparse(sync_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    ssl_val = params.pop("ssl", [None])[0]
    if ssl_val == "require":
        params["sslmode"] = ["require"]
    new_query = urlencode({k: v[0] for k, v in params.items()})
    sync_url = urlunparse(parsed._replace(query=new_query))
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
    migration_error = None
    for attempt in range(1, retries + 1):
        try:
            await asyncio.to_thread(run_migrations)
            migration_error = None
            break
        except Exception as exc:
            migration_error = exc
            if attempt == retries:
                logger.error("Migration step failed after %d attempts: %s", retries, exc)
                import traceback as _tb, sys as _sys
                print("=" * 60, file=_sys.stderr)
                print(f"ERROR: Alembic migration failed after {retries} attempts:", file=_sys.stderr)
                _tb.print_exc(file=_sys.stderr)
                print("=" * 60, file=_sys.stderr)
                _sys.stderr.flush()
                # Non-fatal: app can still serve requests even if migrations fail
                # (tables may already be up to date from a previous deploy)
                logger.warning("Continuing startup despite migration failure — tables may already be current")
                break
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
            # Credentials are resolved from either SUPABASE_S3_* or AWS_* vars
            # by the config validator. MINIO_ENDPOINT holds the full S3 endpoint
            # host+path (e.g. dvibhmdfprwxqjupoxfw.supabase.co/storage/v1/s3).
            if not settings.MINIO_ENDPOINT or not settings.MINIO_ACCESS_KEY or not settings.MINIO_SECRET_KEY:
                raise ValueError(
                    "STORAGE_BACKEND=supabase requires AWS_ENDPOINT_URL (or SUPABASE_PROJECT_REF), "
                    "AWS_ACCESS_KEY_ID (or SUPABASE_S3_ACCESS_KEY_ID), and "
                    "AWS_SECRET_ACCESS_KEY (or SUPABASE_S3_SECRET_ACCESS_KEY) to be set."
                )
            bucket_name = settings.SUPABASE_BUCKET or settings.MINIO_BUCKET
            backend = MinioStorageBackend(
                endpoint=settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                bucket=bucket_name,
                secure=True,  # Supabase always HTTPS
            )
            logger.info(
                "Storage backend: Supabase S3 (endpoint: %s, bucket: %s)",
                settings.MINIO_ENDPOINT,
                bucket_name,
            )
        else:
            bucket_name = settings.MINIO_BUCKET
            backend = MinioStorageBackend(
                endpoint=settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                bucket=bucket_name,
                secure=settings.MINIO_SECURE,
                public_endpoint=settings.MINIO_PUBLIC_ENDPOINT,
            )
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
        import traceback as _tb
        logger.error(
            "StorageService initialisation failed — storage will be unavailable.\n"
            "  backend : %s\n"
            "  endpoint: %s\n"
            "  bucket  : %s\n"
            "  error   : %s\n%s",
            settings.STORAGE_BACKEND,
            settings.MINIO_ENDPOINT or "<not set>",
            locals().get("bucket_name", "<not set>"),
            exc,
            _tb.format_exc(),
        )
        app.state.storage_service = None

    if skip_models:
        app.state.detection_service = None
        app.state.ocr_pipeline = None
        return

    validate_model_files()

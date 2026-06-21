"""
TrafficVision AI — FastAPI application entry point.

Responsibilities
----------------
* Create the FastAPI application instance.
* Register CORS middleware using the ``CORS_ALLOWED_ORIGINS`` environment variable.
* Mount all API routers.
* Manage application lifespan (startup / shutdown) for shared service instances.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan — initialise / teardown shared resources
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan context manager.

    On startup:
      - Creates the async SQLAlchemy session factory.
      - Instantiates StorageService and ensures the MinIO bucket exists.
      - Loads ML model singletons (DetectionService, OCRPipeline).
      - Creates ViolationEngine, EvidenceGenerator, EvidenceUploader.

    All heavy objects are stored on ``app.state`` so that FastAPI Depends
    factories in ``dependencies.py`` can retrieve them without re-instantiation.
    """
    # Deferred imports keep module-level side-effects (heavy ML libs) out of
    # the import chain until the application actually starts.
    from app.startup import run_startup
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    # ------------------------------------------------------------------ DB
    engine = create_async_engine(settings.DATABASE_URL, echo=(settings.APP_ENV == "development"))
    app.state.engine = engine
    app.state.AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    logger.info("Database engine created: %s", settings.DATABASE_URL.split("@")[-1])

    skip_models = settings.APP_ENV == "test"
    await run_startup(app, skip_models=skip_models)

    if not skip_models:
        # ------------------------------------------------------------------ ML Models
        try:
            from app.detection.detector import DetectionService  # type: ignore[import]
            app.state.detection_service = DetectionService(model_dir=settings.MODEL_DIR)
            logger.info("DetectionService loaded from %s", settings.MODEL_DIR)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("DetectionService initialisation failed: %s", exc)
            app.state.detection_service = None

        try:
            from app.ocr.ocr_pipeline import OCRPipeline  # type: ignore[import]
            app.state.ocr_pipeline = OCRPipeline()
            logger.info("OCRPipeline ready")
        except Exception as exc:  # noqa: BLE001
            logger.warning("OCRPipeline initialisation failed: %s", exc)
            app.state.ocr_pipeline = None

    # ------------------------------------------------------------------ Business logic services
    try:
        from app.violation_engine.engine import ViolationEngine  # type: ignore[import]
        app.state.violation_engine = ViolationEngine()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ViolationEngine initialisation failed: %s", exc)
        app.state.violation_engine = None

    try:
        from app.evidence.generator import EvidenceGenerator  # type: ignore[import]
        app.state.evidence_generator = EvidenceGenerator()
    except Exception as exc:  # noqa: BLE001
        logger.warning("EvidenceGenerator initialisation failed: %s", exc)
        app.state.evidence_generator = None

    try:
        from app.evidence.uploader import EvidenceUploader  # type: ignore[import]
        app.state.evidence_uploader = EvidenceUploader(storage_service=app.state.storage_service)
    except Exception as exc:  # noqa: BLE001
        logger.warning("EvidenceUploader initialisation failed: %s", exc)
        app.state.evidence_uploader = None

    logger.info("TrafficVision AI startup complete (env=%s)", settings.APP_ENV)

    yield  # ← application is running

    # ------------------------------------------------------------------ Teardown
    await engine.dispose()
    logger.info("TrafficVision AI shutdown complete")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

def create_app(*, testing: bool = False) -> FastAPI:
    """Factory function that constructs the FastAPI application."""
    app = FastAPI(
        title="TrafficVision AI",
        description="Traffic violation detection platform — REST API",
        version="1.0.0",
        lifespan=None if testing else lifespan,
    )

    # ------------------------------------------------------------------ CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------ Routers
    # Routers are imported lazily here to avoid circular-import issues while
    # individual route modules are being developed incrementally.
    try:
        from app.api.routes.upload import router as upload_router  # type: ignore[import]
        app.include_router(upload_router, tags=["Upload"])
    except ImportError:
        logger.debug("upload router not yet available")

    try:
        from app.api.routes.analyze import router as analyze_router  # type: ignore[import]
        app.include_router(analyze_router, tags=["Analysis"])
    except ImportError as exc:
        logger.warning("analyze router not available: %s", exc)

    try:
        from app.api.routes.violations import router as violations_router  # type: ignore[import]
        app.include_router(violations_router, tags=["Violations"])
    except ImportError:
        logger.debug("violations router not yet available")

    try:
        from app.api.routes.analytics import router as analytics_router  # type: ignore[import]
        app.include_router(analytics_router, tags=["Analytics"])
    except ImportError:
        logger.debug("analytics router not yet available")

    try:
        from app.api.routes.health import router as health_router  # type: ignore[import]
        app.include_router(health_router, tags=["Health"])
    except ImportError:
        logger.debug("health router not yet available")

    return app


app = create_app()

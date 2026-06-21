"""
FastAPI dependency factories.

Each function here is intended to be used with FastAPI's `Depends()` mechanism.
Heavy service instances (DetectionService, OCRPipeline, etc.) are attached to
``app.state`` at startup so they are instantiated exactly once.
"""
from __future__ import annotations

from fastapi import Request

from app.database.session import get_db  # re-export for route-layer convenience

# ---------------------------------------------------------------------------
# Database session
# ---------------------------------------------------------------------------
# ``get_db`` is imported from ``app.database.session`` and re-exported here
# so route handlers can import it from either location:
#
#   from app.dependencies import get_db        (route-layer convenience)
#   from app.database.session import get_db    (direct import)
#
# Both resolve to the same async generator implementation.


# ---------------------------------------------------------------------------
# MinIO / Storage
# ---------------------------------------------------------------------------

def get_storage_service(request: Request):
    """Return the shared StorageService instance from app state."""
    return request.app.state.storage_service


# ---------------------------------------------------------------------------
# ML Services
# ---------------------------------------------------------------------------

def get_detection_service(request: Request):
    """Return the shared DetectionService instance from app state."""
    return request.app.state.detection_service


def get_ocr_pipeline(request: Request):
    """Return the shared OCRPipeline instance from app state."""
    return request.app.state.ocr_pipeline


def get_violation_engine(request: Request):
    """Return the shared ViolationEngine instance from app state."""
    return request.app.state.violation_engine


def get_evidence_generator(request: Request):
    """Return the shared EvidenceGenerator instance from app state."""
    return request.app.state.evidence_generator


def get_evidence_uploader(request: Request):
    """Return the shared EvidenceUploader instance from app state."""
    return request.app.state.evidence_uploader

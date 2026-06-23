"""
OCR pipeline — stub implementation.

PaddleOCR has been removed due to poor results and heavy C-library dependencies
that caused deployment failures.  This stub preserves the full public interface
of OCRPipeline so all callers (AnalysisService, dependencies.py, tests) continue
to work without modification.  Plate text always returns None — plate detection
is simply disabled until a replacement OCR solution is integrated.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class OCRPipeline:
    """
    Stub OCR pipeline.  All methods return None / empty results.

    Replaces the PaddleOCR-based implementation.  Drop in a real OCR engine
    here when ready (e.g. EasyOCR, Tesseract, or a cloud Vision API).
    """

    def __init__(self, model_dir: str = "trained_models") -> None:
        logger.info("OCRPipeline initialised (stub — plate OCR disabled)")

    # ------------------------------------------------------------------
    # Public interface — matches the original PaddleOCR-based signature
    # ------------------------------------------------------------------

    def read_plate(self, crop_bytes: bytes, enhance: bool = False) -> str | None:
        """Return None — OCR disabled."""
        return None

    def read_plate_with_crop(
        self, crop_bytes: bytes
    ) -> tuple[str | None, bytes | None]:
        """Return (None, None) — OCR disabled."""
        return None, None

    def enhance_crop(self, crop_bytes: bytes) -> bytes:
        """Return the crop unchanged — enhancement disabled."""
        return crop_bytes

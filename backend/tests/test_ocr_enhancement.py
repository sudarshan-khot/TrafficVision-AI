"""Unit tests for Real-ESRGAN OCR enhancement pipeline."""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from app.detection.models import BoundingBox, DetectedObject
from app.ocr.ocr_pipeline import OCRPipeline
from app.services.analysis_service import AnalysisService


def test_enhance_crop_success():
    # Mock RealESRGANer and dependencies to avoid real weights load / inference
    mock_upsampler = MagicMock()
    # Mock enhance to return a BGR green numpy array (128x128)
    dummy_enhanced = np.zeros((128, 128, 3), dtype=np.uint8)
    dummy_enhanced[:, :, 1] = 255
    mock_upsampler.enhance.return_value = (dummy_enhanced, None)

    with (
        patch("realesrgan.RealESRGANer", return_value=mock_upsampler),
        patch("basicsr.archs.rrdbnet_arch.RRDBNet"),
        patch("paddleocr.PaddleOCR"),
    ):
        pipeline = OCRPipeline(model_dir="dummy")

        # Create a red 64x64 input image
        img = Image.new("RGB", (64, 64), color=(255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        input_bytes = buf.getvalue()

        enhanced_bytes = pipeline.enhance_crop(input_bytes)
        assert enhanced_bytes is not None

        # Verify output size is 128x128
        enhanced_img = Image.open(io.BytesIO(enhanced_bytes))
        assert enhanced_img.size == (128, 128)


@pytest.mark.asyncio
async def test_read_plates_and_crops_with_yolo_plate():
    # Test that when a number_plate is detected, it is cropped, enhanced, and read
    ocr = MagicMock()
    ocr.enhance_crop = MagicMock(return_value=b"enhanced_bytes")
    ocr.read_plate = MagicMock(return_value="MH12DE1433")
    ocr.read_plate_with_crop = MagicMock()

    analysis = AnalysisService()

    # Create dummy original image bytes (100x100)
    img = Image.new("RGB", (100, 100), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    # Create vehicle and plate objects
    vehicle = DetectedObject(
        id="veh-1",
        cls="car",
        confidence=0.9,
        bounding_box=BoundingBox(x1=10, y1=10, x2=90, y2=90),
    )
    plate = DetectedObject(
        id="plate-1",
        cls="number_plate",
        confidence=0.85,
        bounding_box=BoundingBox(x1=30, y1=40, x2=70, y2=60),
    )

    plate_text_by_vehicle, plate_crops = await analysis._read_plates_and_crops(
        image_bytes, [vehicle, plate], ocr
    )

    assert plate_text_by_vehicle["veh-1"] == "MH12DE1433"
    assert plate_crops["veh-1"] == b"enhanced_bytes"
    ocr.read_plate_with_crop.assert_not_called()


@pytest.mark.asyncio
async def test_read_plates_and_crops_fallback():
    # Test fallback behavior when no number_plate is detected
    ocr = MagicMock()
    ocr.read_plate_with_crop = MagicMock(return_value=("MH12DE1433", b"fallback_crop"))

    analysis = AnalysisService()

    img = Image.new("RGB", (100, 100), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    vehicle = DetectedObject(
        id="veh-1",
        cls="car",
        confidence=0.9,
        bounding_box=BoundingBox(x1=10, y1=10, x2=90, y2=90),
    )

    plate_text_by_vehicle, plate_crops = await analysis._read_plates_and_crops(
        image_bytes, [vehicle], ocr
    )

    assert plate_text_by_vehicle["veh-1"] == "MH12DE1433"
    assert plate_crops["veh-1"] == b"fallback_crop"
    ocr.read_plate_with_crop.assert_called_once()

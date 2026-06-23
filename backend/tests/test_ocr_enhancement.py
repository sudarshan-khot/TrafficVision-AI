"""
Tests for the OCRPipeline stub.

PaddleOCR has been removed — these tests verify that the stub interface
behaves correctly (all methods return None / pass-through bytes without
raising exceptions).
"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from app.ocr.ocr_pipeline import OCRPipeline


def _make_jpeg(width: int = 64, height: int = 64) -> bytes:
    img = Image.new("RGB", (width, height), color=(120, 80, 40))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_ocr_pipeline_instantiates():
    pipeline = OCRPipeline(model_dir="dummy")
    assert pipeline is not None


def test_read_plate_returns_none():
    pipeline = OCRPipeline()
    result = pipeline.read_plate(_make_jpeg())
    assert result is None


def test_read_plate_with_enhance_flag_returns_none():
    pipeline = OCRPipeline()
    result = pipeline.read_plate(_make_jpeg(), enhance=True)
    assert result is None


def test_read_plate_with_crop_returns_none_tuple():
    pipeline = OCRPipeline()
    text, crop = pipeline.read_plate_with_crop(_make_jpeg())
    assert text is None
    assert crop is None


def test_enhance_crop_returns_input_unchanged():
    pipeline = OCRPipeline()
    original = _make_jpeg()
    result = pipeline.enhance_crop(original)
    assert result == original

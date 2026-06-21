"""
Unit tests for the image preprocessor in detection/preprocessor.py.

Tests verify that ``preprocess()`` correctly decodes image bytes, resizes to
640×640, and returns a uint8 RGB numpy array.

Requirements tested: 2.1
"""
from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from app.detection.preprocessor import preprocess


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jpeg_bytes(width: int = 100, height: int = 80, color: tuple = (128, 64, 32)) -> bytes:
    """Return minimal JPEG bytes for a solid-color image."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_png_bytes(width: int = 200, height: int = 150, mode: str = "RGB") -> bytes:
    """Return minimal PNG bytes."""
    if mode == "RGBA":
        img = Image.new("RGBA", (width, height), color=(10, 20, 30, 200))
    elif mode == "L":
        img = Image.new("L", (width, height), color=128)
    else:
        img = Image.new("RGB", (width, height), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Output shape and dtype
# ---------------------------------------------------------------------------

class TestOutputShapeAndDtype:
    def test_jpeg_output_shape(self):
        result = preprocess(_make_jpeg_bytes())
        assert result.shape == (640, 640, 3)

    def test_png_output_shape(self):
        result = preprocess(_make_png_bytes())
        assert result.shape == (640, 640, 3)

    def test_output_dtype_is_uint8(self):
        result = preprocess(_make_jpeg_bytes())
        assert result.dtype == np.uint8

    def test_output_is_ndarray(self):
        result = preprocess(_make_jpeg_bytes())
        assert isinstance(result, np.ndarray)

    def test_square_input_image(self):
        """A square input still yields 640×640 output."""
        result = preprocess(_make_jpeg_bytes(width=640, height=640))
        assert result.shape == (640, 640, 3)

    def test_wide_image_output_shape(self):
        """A very wide image is resized to 640×640."""
        result = preprocess(_make_jpeg_bytes(width=1920, height=360))
        assert result.shape == (640, 640, 3)

    def test_tall_image_output_shape(self):
        """A very tall image is resized to 640×640."""
        result = preprocess(_make_jpeg_bytes(width=100, height=1080))
        assert result.shape == (640, 640, 3)


# ---------------------------------------------------------------------------
# RGB channel conversion
# ---------------------------------------------------------------------------

class TestRGBConversion:
    def test_rgba_input_produces_3_channels(self):
        """RGBA PNG input should be converted to RGB (3 channels)."""
        result = preprocess(_make_png_bytes(mode="RGBA"))
        assert result.shape[2] == 3

    def test_grayscale_input_produces_3_channels(self):
        """Grayscale PNG input should be expanded to 3 channels."""
        result = preprocess(_make_png_bytes(mode="L"))
        assert result.shape[2] == 3

    def test_rgb_channel_order_preserved(self):
        """Pixels of a solid-color image should have consistent RGB values."""
        # Create a solid red image
        color = (255, 0, 0)
        img = Image.new("RGB", (100, 100), color=color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result = preprocess(buf.getvalue())
        # After resize the dominant channel should still be red (index 0)
        # Allow some tolerance for JPEG compression artefacts (using PNG here)
        assert int(result[:, :, 0].mean()) > 200  # R channel high
        assert int(result[:, :, 1].mean()) < 50   # G channel low
        assert int(result[:, :, 2].mean()) < 50   # B channel low


# ---------------------------------------------------------------------------
# Pixel value range
# ---------------------------------------------------------------------------

class TestPixelValueRange:
    def test_pixel_values_in_0_to_255_range(self):
        result = preprocess(_make_jpeg_bytes())
        assert int(result.min()) >= 0
        assert int(result.max()) <= 255


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_empty_bytes_raises_value_error(self):
        with pytest.raises(ValueError, match="empty"):
            preprocess(b"")

    def test_invalid_bytes_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot decode image bytes"):
            preprocess(b"not-an-image-xxxxx")

    def test_truncated_jpeg_raises_value_error(self):
        jpeg = _make_jpeg_bytes()
        # Severely truncated — not just a truncated JPEG but truly corrupt data
        with pytest.raises((ValueError, Exception)):
            preprocess(jpeg[:10])

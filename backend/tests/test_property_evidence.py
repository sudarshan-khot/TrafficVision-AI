"""Property-based tests for EvidenceGenerator (Properties 10, 11)."""
from __future__ import annotations

import io

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PIL import Image

from app.detection.models import BoundingBox
from app.evidence.generator import EvidenceGenerator
from app.violation_engine.types import ViolationInstance, ViolationType


def _make_image_bytes(fmt: str) -> bytes:
    img = Image.new("RGB", (100, 80), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


@given(confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
@settings(max_examples=30)
def test_confidence_formatted_to_two_decimal_places(confidence: float):
    expected = f"{confidence:.2f}"
    assert expected == format(confidence, ".2f")
    parts = expected.split(".")
    assert len(parts) == 2
    assert len(parts[1]) == 2


@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
def test_output_is_always_jpeg(fmt: str):
    gen = EvidenceGenerator()
    violation = ViolationInstance(
        type=ViolationType.TRIPLE_RIDING,
        confidence=0.75,
        bounding_box=BoundingBox(x1=5, y1=5, x2=40, y2=40),
    )
    output = gen.generate(_make_image_bytes(fmt), [violation])
    assert output[:3] == b"\xff\xd8\xff"

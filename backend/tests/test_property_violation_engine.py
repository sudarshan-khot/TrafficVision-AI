"""Property-based tests for ViolationEngine (Property 2)."""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.detection.models import BoundingBox, DetectedObject, DetectionResult
from app.violation_engine.engine import ViolationEngine
from app.violation_engine.types import ViolationType


def _person(helmet: bool, pid: str) -> DetectedObject:
    return DetectedObject(
        id=pid,
        cls="person",
        confidence=0.9,
        bounding_box=BoundingBox(x1=0, y1=0, x2=10, y2=10),
        attributes={"helmet": helmet},
    )


def _motorcycle(riders: int, mid: str) -> DetectedObject:
    return DetectedObject(
        id=mid,
        cls="motorcycle",
        confidence=0.85,
        bounding_box=BoundingBox(x1=0, y1=0, x2=20, y2=20),
        attributes={"rider_count": riders},
    )


@given(
    n_unhelmeted=st.integers(min_value=0, max_value=10),
    m_triple=st.integers(min_value=0, max_value=5),
)
@settings(max_examples=50)
def test_violation_engine_counts(n_unhelmeted: int, m_triple: int):
    objects: list[DetectedObject] = []
    motorcycles: list[DetectedObject] = []

    for i in range(n_unhelmeted):
        objects.append(_person(False, f"p{i}"))
    for i in range(n_unhelmeted):
        objects.append(_person(True, f"ph{i}"))

    for i in range(m_triple):
        moto = _motorcycle(3 + i % 2, f"m{i}")
        objects.append(moto)
        motorcycles.append(moto)

    result = DetectionResult(image_id="img", objects=objects, motorcycles=motorcycles)
    violations = ViolationEngine().evaluate(result)

    helmet_count = sum(1 for v in violations if v.type == ViolationType.HELMET_NON_COMPLIANCE)
    triple_count = sum(1 for v in violations if v.type == ViolationType.TRIPLE_RIDING)

    assert helmet_count == n_unhelmeted
    assert triple_count == m_triple

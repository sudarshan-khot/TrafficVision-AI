"""Tests for ViolationEngine."""
from __future__ import annotations

from app.detection.models import BoundingBox, DetectedObject, DetectionResult
from app.violation_engine.engine import ViolationEngine
from app.violation_engine.types import ViolationType


def _person(helmet: bool | None, obj_id: str = "p1") -> DetectedObject:
    return DetectedObject(
        id=obj_id,
        cls="person",
        confidence=0.9,
        bounding_box=BoundingBox(x1=0, y1=0, x2=10, y2=10),
        attributes={"helmet": helmet},
    )


def _motorcycle(rider_count: int, obj_id: str = "m1") -> DetectedObject:
    return DetectedObject(
        id=obj_id,
        cls="motorcycle",
        confidence=0.85,
        bounding_box=BoundingBox(x1=0, y1=0, x2=20, y2=20),
        attributes={"rider_count": rider_count},
    )


class TestViolationEngine:
    def test_helmet_non_compliance_count(self):
        result = DetectionResult(
            image_id="img-1",
            objects=[
                _person(False, "p1"),
                _person(False, "p2"),
                _person(True, "p3"),
            ],
        )
        violations = ViolationEngine().evaluate(result)
        helmet_violations = [
            v for v in violations if v.type == ViolationType.HELMET_NON_COMPLIANCE
        ]
        assert len(helmet_violations) == 2

    def test_triple_riding_count(self):
        moto = _motorcycle(3)
        result = DetectionResult(
            image_id="img-1",
            objects=[moto],
            motorcycles=[moto],
        )
        violations = ViolationEngine().evaluate(result)
        triple = [v for v in violations if v.type == ViolationType.TRIPLE_RIDING]
        assert len(triple) == 1
        assert triple[0].vehicle_id == "m1"

    def test_stub_rules_never_match(self):
        result = DetectionResult(
            image_id="img-1",
            objects=[_person(False)],
        )
        violations = ViolationEngine().evaluate(result)
        stub_types = {
            ViolationType.WRONG_SIDE_DRIVING,
            ViolationType.STOP_LINE_VIOLATION,
            ViolationType.ILLEGAL_PARKING,
        }
        assert stub_types.isdisjoint({v.type for v in violations})

"""
Violation rule implementations for TrafficVision AI.

Requirements: 2.2, 2.3, 2.11
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.detection.models import DetectedObject
from app.violation_engine.types import ViolationType


class Rule(ABC):
    """Abstract base for a single violation detection rule."""

    violation_type: ViolationType

    @abstractmethod
    def matches(self, obj: DetectedObject) -> bool:
        """Return True when *obj* satisfies this violation rule."""


class HelmetNonComplianceRule(Rule):
    """Matches persons detected without a helmet."""

    violation_type = ViolationType.HELMET_NON_COMPLIANCE

    def matches(self, obj: DetectedObject) -> bool:
        return obj.cls == "person" and obj.attributes.get("helmet") is False


class TripleRidingRule(Rule):
    """Matches motorcycles carrying three or more riders."""

    violation_type = ViolationType.TRIPLE_RIDING

    def matches(self, obj: DetectedObject) -> bool:
        return (
            obj.cls == "motorcycle"
            and int(obj.attributes.get("rider_count", 0)) >= 3
        )


class WrongSideDrivingRule(Rule):
    """Stub rule — always returns False in the MVP."""

    violation_type = ViolationType.WRONG_SIDE_DRIVING

    def matches(self, obj: DetectedObject) -> bool:
        return False


class StopLineViolationRule(Rule):
    """Stub rule — always returns False in the MVP."""

    violation_type = ViolationType.STOP_LINE_VIOLATION

    def matches(self, obj: DetectedObject) -> bool:
        return False


class IllegalParkingRule(Rule):
    """Stub rule — always returns False in the MVP."""

    violation_type = ViolationType.ILLEGAL_PARKING

    def matches(self, obj: DetectedObject) -> bool:
        return False

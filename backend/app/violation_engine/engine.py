"""
Pure violation evaluation engine.

Requirements: 2.2, 2.3
"""
from __future__ import annotations

from app.detection.models import DetectionResult
from app.violation_engine.rules import (
    HelmetNonComplianceRule,
    IllegalParkingRule,
    Rule,
    StopLineViolationRule,
    TripleRidingRule,
    WrongSideDrivingRule,
)
from app.violation_engine.types import ViolationInstance


class ViolationEngine:
    """Evaluate detection results against registered violation rules."""

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self._rules = rules or [
            HelmetNonComplianceRule(),
            TripleRidingRule(),
            WrongSideDrivingRule(),
            StopLineViolationRule(),
            IllegalParkingRule(),
        ]

    def evaluate(self, detection_result: DetectionResult) -> list[ViolationInstance]:
        """
        Apply all rules to *detection_result* and return violation instances.

        This is a pure function with no I/O side effects.
        """
        violations: list[ViolationInstance] = []

        for obj in detection_result.objects:
            for rule in self._rules:
                if rule.matches(obj):
                    violations.append(
                        ViolationInstance(
                            type=rule.violation_type,
                            confidence=obj.confidence,
                            bounding_box=obj.bounding_box,
                            vehicle_id=obj.associated_vehicle_id or (
                                obj.id if obj.cls == "motorcycle" else None
                            ),
                        )
                    )

        return violations

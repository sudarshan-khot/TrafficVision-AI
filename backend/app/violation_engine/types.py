"""
Violation type definitions for the TrafficVision AI violation engine.

Requirements: 2.2, 2.3, 2.11
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.detection.models import BoundingBox


class ViolationType(str, Enum):
    """Supported traffic violation categories."""

    HELMET_NON_COMPLIANCE = "HELMET_NON_COMPLIANCE"
    TRIPLE_RIDING = "TRIPLE_RIDING"
    WRONG_SIDE_DRIVING = "WRONG_SIDE_DRIVING"
    STOP_LINE_VIOLATION = "STOP_LINE_VIOLATION"
    ILLEGAL_PARKING = "ILLEGAL_PARKING"


class ViolationInstance(BaseModel):
    """A single detected violation before database persistence."""

    type: ViolationType
    confidence: float = Field(..., ge=0.0, le=1.0)
    bounding_box: BoundingBox
    vehicle_id: str | None = None
    plate_number: str | None = None

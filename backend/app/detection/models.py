"""
Pydantic models for the TrafficVision AI detection pipeline.

These models represent the output of the ML inference step and are consumed
by the ViolationEngine, EvidenceGenerator, and persistence layer.

Classes
-------
* ``BoundingBox``     — Pixel-coordinate box (x1, y1, x2, y2).
* ``DetectedObject``  — A single YOLO detection result (class, confidence,
                        bounding box, arbitrary attributes, and optional link
                        to an associated vehicle).
* ``DetectionResult`` — Full inference output for one image, including a
                        convenience ``motorcycles`` sub-list.

Requirements: 2.1
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """
    Axis-aligned bounding box in pixel coordinates.

    All values are integers representing absolute pixel positions in the
    original (pre-resize) image coordinate space.

    Attributes
    ----------
    x1 : int
        Left edge of the box (inclusive).
    y1 : int
        Top edge of the box (inclusive).
    x2 : int
        Right edge of the box (exclusive).
    y2 : int
        Bottom edge of the box (exclusive).
    """

    x1: int = Field(..., description="Left edge of the bounding box (pixels)")
    y1: int = Field(..., description="Top edge of the bounding box (pixels)")
    x2: int = Field(..., description="Right edge of the bounding box (pixels)")
    y2: int = Field(..., description="Bottom edge of the bounding box (pixels)")

    model_config = {"frozen": True}


class DetectedObject(BaseModel):
    """
    A single object detected by YOLOv8m inference.

    Each ``DetectedObject`` corresponds to one bounding-box prediction from
    the model.  The ``attributes`` dict carries domain-specific metadata set
    by ``DetectionService`` after running the secondary helmet model and
    counting riders; downstream consumers (``ViolationEngine``, rules) read
    keys such as ``"helmet"`` and ``"rider_count"`` from this dict.

    Attributes
    ----------
    id : str
        Unique identifier for this detection within a single inference run
        (UUID string assigned by ``DetectionService``).
    cls : str
        Human-readable class label, e.g. ``"motorcycle"``, ``"person"``,
        ``"number_plate"``, ``"car"``, ``"truck"``, ``"bus"``.
    confidence : float
        ML model confidence score in the range [0.0, 1.0].
    bounding_box : BoundingBox
        Pixel-coordinate bounding box for this detection.
    attributes : dict
        Arbitrary key/value metadata attached by ``DetectionService``.
        Standard keys used by the violation engine:

        * ``"helmet"`` (``bool | None``) — ``True`` if a helmet is detected,
          ``False`` if not, ``None`` if not applicable (non-person class).
        * ``"rider_count"`` (``int``) — number of riders on a motorcycle
          (set only when ``cls == "motorcycle"``).

    associated_vehicle_id : str | None
        The ``id`` of the ``DetectedObject`` representing the vehicle that
        this object (typically a ``"person"`` or ``"number_plate"``) is
        associated with.  ``None`` when there is no vehicle association.
    """

    id: str = Field(..., description="Unique detection ID within this inference run")
    cls: str = Field(
        ...,
        description=(
            'Detected class label, e.g. "motorcycle", "person", "number_plate"'
        ),
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence score in [0.0, 1.0]",
    )
    bounding_box: BoundingBox = Field(
        ..., description="Pixel-coordinate bounding box"
    )
    attributes: dict = Field(
        default_factory=dict,
        description=(
            "Domain-specific metadata dict. "
            'Keys: "helmet" (bool|None), "rider_count" (int).'
        ),
    )
    associated_vehicle_id: str | None = Field(
        default=None,
        description=(
            "ID of the associated vehicle DetectedObject, or None if absent"
        ),
    )


class DetectionResult(BaseModel):
    """
    Full inference output for one uploaded image.

    ``DetectionService.detect()`` returns a single ``DetectionResult`` per
    image.  The ``objects`` list contains every YOLO detection; the
    ``motorcycles`` list is a convenience view — a pre-filtered sub-list of
    objects whose ``cls == "motorcycle"`` — so that the ``ViolationEngine``
    does not need to filter the full list itself.

    Attributes
    ----------
    image_id : str
        UUID of the source image as recorded in MinIO / the database.
    objects : list[DetectedObject]
        All detected objects from both the base YOLOv8m model and the
        secondary helmet detection model.
    motorcycles : list[DetectedObject]
        Convenience sub-list: every ``DetectedObject`` in ``objects`` where
        ``cls == "motorcycle"``.  Populated by ``DetectionService`` at the
        time of result construction; consumers should treat this as read-only.
    """

    image_id: str = Field(
        ..., description="UUID of the source image"
    )
    objects: list[DetectedObject] = Field(
        default_factory=list,
        description="All detected objects for this image",
    )
    motorcycles: list[DetectedObject] = Field(
        default_factory=list,
        description=(
            'Convenience sub-list of objects where cls == "motorcycle"'
        ),
    )

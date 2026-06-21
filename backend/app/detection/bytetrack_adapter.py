"""
ByteTrack adapter stub for future video-stream tracking support.

This module is intentionally a no-op in the MVP.  When video support is
added, :class:`ByteTrackAdapter` will wrap the ByteTrack multi-object
tracker and maintain consistent track IDs across frames.

Requirements: 7.1 (future extensibility hook)
"""
from __future__ import annotations

from app.detection.models import DetectedObject


class ByteTrackAdapter:
    """
    Placeholder adapter for ByteTrack multi-object tracking.

    In the static-image MVP this class is not invoked.  The ``update()``
    method is reserved for future video-frame processing where detections
    from consecutive frames need stable track identifiers.
    """

    def update(self, detections: list[DetectedObject]) -> list[DetectedObject]:
        """
        Accept per-frame detections and return tracked detections.

        Parameters
        ----------
        detections:
            Raw detections from a single video frame.

        Returns
        -------
        list[DetectedObject]
            Tracked detections with stable IDs (not yet implemented).
        """
        return detections

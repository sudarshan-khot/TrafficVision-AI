"""Unit tests for crop-based detection in detector.py."""
from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest
from PIL import Image

from app.detection.detector import DetectionService
from app.detection.models import BoundingBox, DetectedObject


def _make_dummy_image(w: int = 100, h: int = 100) -> bytes:
    img = Image.new("RGB", (w, h), color=(100, 120, 140))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestDetectionServiceCustom:
    def test_detect_motorcycle_crops_and_maps_riders(self):
        # Create DetectionService without calling __init__ to avoid model loading
        service = DetectionService.__new__(DetectionService)

        # Mock model one (_yolo)
        mock_yolo = MagicMock()
        mock_yolo.names = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle"}
        
        # Mock first prediction result (motorcycle detected)
        mock_box = MagicMock()
        mock_box.xyxy = [[10.0, 10.0, 50.0, 50.0]]  # in 640x640 preprocessed space
        mock_box.conf = [0.9]
        mock_box.cls = [3]  # motorcycle
        
        mock_result = MagicMock()
        mock_result.boxes = mock_box
        mock_result.names = mock_yolo.names
        mock_yolo.predict.return_value = [mock_result]
        service._yolo = mock_yolo

        # Mock model two (_helmet_model)
        mock_helmet_model = MagicMock()
        # Case: Fine-tuned model names (contains helmet-use classes)
        mock_helmet_model.names = {
            0: "with_helmet",
            1: "without_helmet",
            2: "person"
        }
        
        # Mock crop prediction result: rider without helmet
        mock_crop_box = MagicMock()
        mock_crop_box.xyxy = [[5.0, 5.0, 25.0, 25.0]]  # relative to crop
        mock_crop_box.conf = [0.85]
        mock_crop_box.cls = [1]  # without_helmet
        
        mock_crop_result = MagicMock()
        mock_crop_result.boxes = mock_crop_box
        mock_crop_result.names = mock_helmet_model.names
        mock_helmet_model.predict.return_value = [mock_crop_result]
        service._helmet_model = mock_helmet_model

        # Execute detect on a 200x200 image
        image_bytes = _make_dummy_image(w=200, h=200)
        res = service.detect(image_bytes, image_id="test-image-uuid")

        # Assertions
        assert res.image_id == "test-image-uuid"
        
        # Find motorcycle and rider
        motos = [obj for obj in res.objects if obj.cls == "motorcycle"]
        riders = [obj for obj in res.objects if obj.cls == "person" and obj.associated_vehicle_id is not None]
        
        assert len(motos) == 1
        assert len(riders) == 1
        
        moto = motos[0]
        rider = riders[0]
        
        # Motorcycle checks
        assert moto.attributes["rider_count"] == 1
        
        # Bounding boxes check
        # Motorcyle bbox: scaled from 640x640 to 200x200
        # Box coordinates: x1=10, y1=10, x2=50, y2=50
        # Scaling factor: sx = 200/640 = 0.3125, sy = 200/640 = 0.3125
        # x1 = 10 * 0.3125 = 3
        # y1 = 10 * 0.3125 = 3
        # x2 = 50 * 0.3125 = 15
        # y2 = 50 * 0.3125 = 15
        assert moto.bounding_box.x1 == 3
        assert moto.bounding_box.y1 == 3
        
        # Rider bbox should be mapped: moto_x1 + crop_x1
        # moto_x1 = 3, crop_x1 = 5
        # x1_orig = 3 + 5 = 8
        assert rider.bounding_box.x1 == 8
        assert rider.bounding_box.y1 == 8
        assert rider.bounding_box.x2 == 28
        assert rider.bounding_box.y2 == 28
        
        # Rider attributes
        assert rider.attributes["helmet"] is False  # mapped from class 1 (without_helmet)

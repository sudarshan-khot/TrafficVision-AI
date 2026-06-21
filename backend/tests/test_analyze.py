"""API tests for POST /analyze."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.dependencies import get_detection_service, get_storage_service


class TestAnalyze:
    def test_success(self, client, mock_storage, sample_jpeg):
        mock_storage.get_object = AsyncMock(return_value=sample_jpeg)
        response = client.post(
            "/analyze",
            json={
                "image_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "object_path": "original/f47ac10b-58cc-4372-a567-0e02b2c3d479.jpg",
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["image_id"] == "f47ac10b-58cc-4372-a567-0e02b2c3d479"
        assert "violations" in data
        assert "vehicles" in data
        assert "processing_time_ms" in data

    def test_image_not_found(self, client, mock_storage):
        mock_storage.get_object = AsyncMock(side_effect=Exception("missing"))
        response = client.post(
            "/analyze",
            json={
                "image_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "object_path": "original/missing.jpg",
            },
        )
        assert response.status_code == 404

    def test_detection_failure(self, client, mock_storage, mock_detector, sample_jpeg):
        mock_storage.get_object = AsyncMock(return_value=sample_jpeg)
        mock_detector.detect = MagicMock(side_effect=RuntimeError("boom"))
        response = client.post(
            "/analyze",
            json={
                "image_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "object_path": "original/test.jpg",
            },
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Detection failed"

    def test_services_unavailable(self, client):
        from app.dependencies import get_detection_service, get_ocr_pipeline, get_storage_service

        client.app.dependency_overrides[get_storage_service] = lambda: None
        client.app.dependency_overrides[get_detection_service] = lambda: None
        client.app.dependency_overrides[get_ocr_pipeline] = lambda: None
        response = client.post(
            "/analyze",
            json={"image_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"},
        )
        assert response.status_code == 503

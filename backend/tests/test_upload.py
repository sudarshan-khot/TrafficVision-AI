"""API tests for POST /upload-image."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.storage_service import StorageUnavailableError


class TestUploadImage:
    def test_success(self, client, sample_jpeg, mock_storage):
        mock_storage.put_object = AsyncMock(return_value="original/abc.jpg")
        response = client.post(
            "/upload-image",
            files={"file": ("test.jpg", sample_jpeg, "image/jpeg")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "image_id" in data
        assert data["object_path"].startswith("original/")
        assert "uploaded_at" in data

    def test_file_too_large(self, client):
        large = b"x" * (20 * 1024 * 1024 + 1)
        response = client.post(
            "/upload-image",
            files={"file": ("big.jpg", large, "image/jpeg")},
        )
        assert response.status_code == 413

    def test_unsupported_media_type(self, client):
        response = client.post(
            "/upload-image",
            files={"file": ("test.gif", b"GIF89a", "image/gif")},
        )
        assert response.status_code == 415

    def test_storage_unavailable(self, client, sample_jpeg, mock_storage):
        mock_storage.put_object = AsyncMock(side_effect=StorageUnavailableError("down"))
        response = client.post(
            "/upload-image",
            files={"file": ("test.jpg", sample_jpeg, "image/jpeg")},
        )
        assert response.status_code == 503

    def test_storage_none_returns_503(self, client, sample_jpeg):
        from app.dependencies import get_storage_service

        client.app.dependency_overrides[get_storage_service] = lambda: None
        response = client.post(
            "/upload-image",
            files={"file": ("test.jpg", sample_jpeg, "image/jpeg")},
        )
        assert response.status_code == 503

    def test_object_path_contains_image_id(self, client, sample_jpeg, mock_storage):
        async def _put(prefix, name, data, content_type="application/octet-stream"):
            return f"{prefix}/{name}"

        mock_storage.put_object = AsyncMock(side_effect=_put)
        response = client.post(
            "/upload-image",
            files={"file": ("test.jpg", sample_jpeg, "image/jpeg")},
        )
        data = response.json()
        assert data["image_id"] in data["object_path"]

"""
Unit tests for StorageService (MinIO wrapper).

Tests use unittest.mock to patch the underlying Minio client so no live
MinIO instance is required.

Requirements tested: 1.1, 1.5, 4.3, 8.3
"""
from __future__ import annotations

import asyncio
import io
from datetime import timedelta
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from minio.error import S3Error
from urllib3.exceptions import MaxRetryError, NewConnectionError

from app.services.storage_service import (
    StorageService,
    StorageUnavailableError,
    _is_connectivity_error,
    _wrap_connectivity,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_minio_client():
    """Return a MagicMock that stands in for the real Minio client."""
    return MagicMock()


@pytest.fixture()
def storage(mock_minio_client):
    """StorageService with a patched Minio client."""
    svc = StorageService(
        endpoint="localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket="test-bucket",
        secure=False,
    )
    svc._client = mock_minio_client
    return svc


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------

class TestIsConnectivityError:
    def test_max_retry_error_is_connectivity(self):
        exc = MaxRetryError(pool=None, url="/")
        assert _is_connectivity_error(exc) is True

    def test_connection_error_is_connectivity(self):
        assert _is_connectivity_error(ConnectionError()) is True

    def test_connection_refused_is_connectivity(self):
        assert _is_connectivity_error(ConnectionRefusedError()) is True

    def test_value_error_is_not_connectivity(self):
        assert _is_connectivity_error(ValueError("bad value")) is False

    def test_s3error_no_such_key_is_not_connectivity(self):
        exc = S3Error(
            code="NoSuchKey",
            message="key not found",
            resource="/bucket/key",
            request_id="req-1",
            host_id="host-1",
            response=None,
        )
        assert _is_connectivity_error(exc) is False

    def test_s3error_with_connectivity_cause_is_connectivity(self):
        exc = S3Error(
            code="ServiceUnavailable",
            message="unavailable",
            resource="/",
            request_id="req-2",
            host_id="host-2",
            response=None,
        )
        exc.__cause__ = MaxRetryError(pool=None, url="/")
        assert _is_connectivity_error(exc) is True


class TestWrapConnectivity:
    def test_returns_storage_unavailable_error(self):
        original = ConnectionError("refused")
        wrapped = _wrap_connectivity(original, "test_op")
        assert isinstance(wrapped, StorageUnavailableError)
        assert wrapped.cause is original
        assert "test_op" in str(wrapped)


# ---------------------------------------------------------------------------
# ensure_bucket tests
# ---------------------------------------------------------------------------

class TestEnsureBucket:
    def test_creates_bucket_when_absent(self, storage, mock_minio_client):
        mock_minio_client.bucket_exists.return_value = False
        asyncio.run(storage.ensure_bucket())
        mock_minio_client.bucket_exists.assert_called_once_with("test-bucket")
        mock_minio_client.make_bucket.assert_called_once_with("test-bucket")

    def test_skips_creation_when_bucket_exists(self, storage, mock_minio_client):
        mock_minio_client.bucket_exists.return_value = True
        asyncio.run(storage.ensure_bucket())
        mock_minio_client.bucket_exists.assert_called_once_with("test-bucket")
        mock_minio_client.make_bucket.assert_not_called()

    def test_raises_storage_unavailable_on_connection_error(self, storage, mock_minio_client):
        mock_minio_client.bucket_exists.side_effect = ConnectionError("refused")
        with pytest.raises(StorageUnavailableError):
            asyncio.run(storage.ensure_bucket())

    def test_raises_storage_unavailable_on_max_retry_error(self, storage, mock_minio_client):
        mock_minio_client.bucket_exists.side_effect = MaxRetryError(pool=None, url="/")
        with pytest.raises(StorageUnavailableError):
            asyncio.run(storage.ensure_bucket())

    def test_ignores_already_owned_bucket_race_condition(self, storage, mock_minio_client):
        mock_minio_client.bucket_exists.return_value = False
        already_owned = S3Error(
            code="BucketAlreadyOwnedByYou",
            message="bucket owned",
            resource="/test-bucket",
            request_id="req-1",
            host_id="host-1",
            response=None,
        )
        mock_minio_client.make_bucket.side_effect = already_owned
        # Should NOT raise
        asyncio.run(storage.ensure_bucket())


# ---------------------------------------------------------------------------
# put_object tests
# ---------------------------------------------------------------------------

class TestPutObject:
    def test_returns_correct_path_with_prefix(self, storage, mock_minio_client):
        path = asyncio.run(
            storage.put_object("original", "abc123.jpg", b"fakejpeg", "image/jpeg")
        )
        assert path == "original/abc123.jpg"

    def test_calls_minio_put_object(self, storage, mock_minio_client):
        asyncio.run(
            storage.put_object("annotated", "img_annotated.jpg", b"data", "image/jpeg")
        )
        mock_minio_client.put_object.assert_called_once()
        call_args = mock_minio_client.put_object.call_args
        # Positional args: bucket, object_path, data, length
        assert call_args[0][0] == "test-bucket"
        assert call_args[0][1] == "annotated/img_annotated.jpg"

    def test_accepts_file_like_object(self, storage, mock_minio_client):
        data = io.BytesIO(b"file-content")
        path = asyncio.run(storage.put_object("crops", "plate_1.jpg", data, "image/jpeg"))
        assert path == "crops/plate_1.jpg"

    def test_raises_storage_unavailable_on_connection_error(self, storage, mock_minio_client):
        mock_minio_client.put_object.side_effect = ConnectionError("refused")
        with pytest.raises(StorageUnavailableError):
            asyncio.run(storage.put_object("original", "img.jpg", b"data", "image/jpeg"))

    def test_raises_storage_unavailable_on_max_retry(self, storage, mock_minio_client):
        mock_minio_client.put_object.side_effect = MaxRetryError(pool=None, url="/")
        with pytest.raises(StorageUnavailableError):
            asyncio.run(storage.put_object("original", "img.jpg", b"data", "image/jpeg"))

    def test_correct_content_type_passed(self, storage, mock_minio_client):
        asyncio.run(storage.put_object("original", "img.png", b"png-data", "image/png"))
        call_kwargs = mock_minio_client.put_object.call_args[1]
        assert call_kwargs.get("content_type") == "image/png"


# ---------------------------------------------------------------------------
# get_object tests
# ---------------------------------------------------------------------------

class TestGetObject:
    def _make_response_mock(self, data: bytes) -> MagicMock:
        """Create a mock HTTP response whose read() returns data."""
        resp = MagicMock()
        resp.read.return_value = data
        return resp

    def test_returns_bytes(self, storage, mock_minio_client):
        mock_minio_client.get_object.return_value = self._make_response_mock(b"image-data")
        result = asyncio.run(storage.get_object("original/abc123.jpg"))
        assert result == b"image-data"

    def test_calls_minio_get_object_with_correct_args(self, storage, mock_minio_client):
        mock_minio_client.get_object.return_value = self._make_response_mock(b"x")
        asyncio.run(storage.get_object("original/test.jpg"))
        mock_minio_client.get_object.assert_called_once_with("test-bucket", "original/test.jpg")

    def test_raises_storage_unavailable_on_connection_error(self, storage, mock_minio_client):
        mock_minio_client.get_object.side_effect = ConnectionError("refused")
        with pytest.raises(StorageUnavailableError):
            asyncio.run(storage.get_object("original/img.jpg"))

    def test_raises_s3error_for_nonexistent_key(self, storage, mock_minio_client):
        exc = S3Error(
            code="NoSuchKey",
            message="key not found",
            resource="/test-bucket/missing.jpg",
            request_id="req-1",
            host_id="host-1",
            response=None,
        )
        mock_minio_client.get_object.side_effect = exc
        with pytest.raises(S3Error):
            asyncio.run(storage.get_object("missing.jpg"))


# ---------------------------------------------------------------------------
# get_presigned_url tests
# ---------------------------------------------------------------------------

class TestGetPresignedUrl:
    def test_returns_url_string(self, storage, mock_minio_client):
        mock_minio_client.presigned_get_object.return_value = (
            "http://localhost:9000/test-bucket/annotated/img.jpg?X-Amz-Expires=3600"
        )
        url = asyncio.run(storage.get_presigned_url("annotated/img.jpg"))
        assert isinstance(url, str)
        assert "annotated/img.jpg" in url

    def test_default_expiry_is_3600_seconds(self, storage, mock_minio_client):
        mock_minio_client.presigned_get_object.return_value = "http://example.com/url"
        asyncio.run(storage.get_presigned_url("annotated/img.jpg"))
        call_kwargs = mock_minio_client.presigned_get_object.call_args[1]
        assert call_kwargs.get("expires") == timedelta(seconds=3600)

    def test_custom_expiry_is_propagated(self, storage, mock_minio_client):
        mock_minio_client.presigned_get_object.return_value = "http://example.com/url"
        asyncio.run(storage.get_presigned_url("annotated/img.jpg", expiry_seconds=7200))
        call_kwargs = mock_minio_client.presigned_get_object.call_args[1]
        assert call_kwargs.get("expires") == timedelta(seconds=7200)

    def test_raises_storage_unavailable_on_connection_error(self, storage, mock_minio_client):
        mock_minio_client.presigned_get_object.side_effect = ConnectionError("refused")
        with pytest.raises(StorageUnavailableError):
            asyncio.run(storage.get_presigned_url("annotated/img.jpg"))

    def test_raises_storage_unavailable_on_new_connection_error(self, storage, mock_minio_client):
        mock_minio_client.presigned_get_object.side_effect = NewConnectionError(
            conn=None, message="failed"
        )
        with pytest.raises(StorageUnavailableError):
            asyncio.run(storage.get_presigned_url("annotated/img.jpg"))


# ---------------------------------------------------------------------------
# StorageUnavailableError tests
# ---------------------------------------------------------------------------

class TestStorageUnavailableError:
    def test_default_message(self):
        err = StorageUnavailableError()
        assert "unavailable" in str(err).lower()

    def test_custom_message(self):
        err = StorageUnavailableError("custom message")
        assert str(err) == "custom message"

    def test_cause_stored(self):
        cause = ConnectionError("refused")
        err = StorageUnavailableError("msg", cause=cause)
        assert err.cause is cause

    def test_is_exception_subclass(self):
        assert issubclass(StorageUnavailableError, Exception)

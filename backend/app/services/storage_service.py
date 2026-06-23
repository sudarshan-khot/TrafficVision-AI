"""
Object storage abstraction for TrafficVision AI.

Two storage backends are supported, both using the MinIO Python SDK (S3-compatible):

* **MinIO** (``STORAGE_BACKEND=minio``) — local dockerized MinIO for development.
* **Supabase S3** (``STORAGE_BACKEND=supabase``) — Supabase object storage in production,
  accessed via its S3-compatible endpoint using S3 Access Key ID / Secret Access Key
  credentials from the Supabase dashboard (Storage → S3 Access).

Both backends are handled by :class:`MinioStorageBackend` because Supabase exposes a
fully S3-compatible API at ``https://<project-ref>.supabase.co/storage/v1/s3``.

:class:`StorageService` is the public async facade consumed by the rest of the app.

Custom exceptions
-----------------
* :class:`StorageUnavailableError` — raised for any connectivity-level failure.
  Callers that map storage failures to HTTP 503 only need to catch this one type.
"""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import timedelta
from typing import BinaryIO

from minio import Minio
from minio.error import S3Error
from urllib3.exceptions import MaxRetryError, NewConnectionError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class StorageUnavailableError(Exception):
    """Raised when the storage backend cannot be reached."""

    def __init__(
        self,
        message: str = "Storage service unavailable",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.cause = cause


# ---------------------------------------------------------------------------
# Connectivity helpers
# ---------------------------------------------------------------------------


def _is_connectivity_error(exc: Exception) -> bool:
    """Return True if *exc* represents a network / connectivity failure."""
    if isinstance(exc, (MaxRetryError, NewConnectionError, ConnectionError, ConnectionRefusedError)):
        return True
    if isinstance(exc, S3Error):
        cause = exc.__cause__ or exc.__context__
        if cause is not None and isinstance(cause, (MaxRetryError, NewConnectionError, ConnectionError)):
            return True
    return False


def _wrap_connectivity(exc: Exception, operation: str) -> StorageUnavailableError:
    msg = f"Storage unavailable during '{operation}': {exc}"
    logger.error(msg)
    return StorageUnavailableError(msg, cause=exc)


# ---------------------------------------------------------------------------
# MinioStorageBackend — handles both local MinIO and Supabase S3
# ---------------------------------------------------------------------------


class MinioStorageBackend:
    """
    S3-compatible storage backend using the MinIO Python SDK.

    Works for:
    - Local Docker MinIO  (``STORAGE_BACKEND=minio``)
    - Supabase S3         (``STORAGE_BACKEND=supabase``)
      endpoint: ``<project-ref>.supabase.co/storage/v1/s3``
      credentials: S3 Access Key ID + Secret from Supabase Storage → S3 Access

    Parameters
    ----------
    endpoint:
        Host (+ optional port) without scheme, e.g. ``"localhost:9000"`` or
        ``"abcxyz.supabase.co/storage/v1/s3"``.
    access_key:
        S3 Access Key ID.
    secret_key:
        S3 Secret Access Key.
    bucket:
        Bucket name.
    secure:
        Use HTTPS when ``True``.  Always ``True`` for Supabase.
    public_endpoint:
        Optional separate host used only for generating presigned URLs
        (useful when the internal Docker hostname differs from the public one).
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
        public_endpoint: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region="us-east-1",
        )
        self._public_client = (
            Minio(
                public_endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure,
                region="us-east-1",
            )
            if public_endpoint
            else None
        )

    @property
    def _url_client(self) -> Minio:
        return self._public_client or self._client

    # ------------------------------------------------------------------ ops

    def ensure_bucket(self) -> None:
        """Create the bucket if it doesn't exist (MinIO). No-op for Supabase where
        buckets are pre-created in the dashboard — existence is verified by a
        lightweight connectivity check instead."""
        try:
            exists = self._client.bucket_exists(self._bucket)
        except (MaxRetryError, NewConnectionError, ConnectionError, ConnectionRefusedError) as exc:
            raise _wrap_connectivity(exc, "ensure_bucket") from exc
        except S3Error as exc:
            if _is_connectivity_error(exc):
                raise _wrap_connectivity(exc, "ensure_bucket") from exc
            raise

        if not exists:
            try:
                self._client.make_bucket(self._bucket)
                logger.info("Created bucket: %s", self._bucket)
            except (MaxRetryError, NewConnectionError, ConnectionError, ConnectionRefusedError) as exc:
                raise _wrap_connectivity(exc, "make_bucket") from exc
            except S3Error as exc:
                if exc.code == "BucketAlreadyOwnedByYou":
                    logger.debug("Bucket race condition — already owned: %s", self._bucket)
                elif _is_connectivity_error(exc):
                    raise _wrap_connectivity(exc, "make_bucket") from exc
                else:
                    raise
        else:
            logger.debug("Bucket already exists: %s", self._bucket)

    def put_object(self, object_path: str, data: bytes, content_type: str) -> None:
        try:
            self._client.put_object(
                self._bucket,
                object_path,
                io.BytesIO(data),
                len(data),
                content_type=content_type,
            )
        except (MaxRetryError, NewConnectionError, ConnectionError, ConnectionRefusedError) as exc:
            raise _wrap_connectivity(exc, f"put_object({object_path})") from exc
        except S3Error as exc:
            if _is_connectivity_error(exc):
                raise _wrap_connectivity(exc, f"put_object({object_path})") from exc
            raise

    def get_object(self, path: str) -> bytes:
        try:
            response = self._client.get_object(self._bucket, path)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except (MaxRetryError, NewConnectionError, ConnectionError, ConnectionRefusedError) as exc:
            raise _wrap_connectivity(exc, f"get_object({path})") from exc
        except S3Error as exc:
            if _is_connectivity_error(exc):
                raise _wrap_connectivity(exc, f"get_object({path})") from exc
            raise

    def get_presigned_url(self, path: str, expiry_seconds: int = 3600) -> str:
        try:
            return self._url_client.presigned_get_object(
                self._bucket,
                path,
                expires=timedelta(seconds=expiry_seconds),
            )
        except (MaxRetryError, NewConnectionError, ConnectionError, ConnectionRefusedError) as exc:
            raise _wrap_connectivity(exc, f"get_presigned_url({path})") from exc
        except S3Error as exc:
            if _is_connectivity_error(exc):
                raise _wrap_connectivity(exc, f"get_presigned_url({path})") from exc
            raise


# ---------------------------------------------------------------------------
# StorageService — async facade
# ---------------------------------------------------------------------------


class StorageService:
    """
    Async-friendly facade over :class:`MinioStorageBackend`.

    All blocking SDK calls are dispatched via :func:`asyncio.to_thread` so
    the FastAPI event loop stays responsive.

    Parameters
    ----------
    backend:
        A :class:`MinioStorageBackend` instance (MinIO or Supabase S3).
    bucket:
        Bucket name — stored for log messages only.
    """

    def __init__(self, backend: MinioStorageBackend, bucket: str) -> None:
        self._backend = backend
        self._bucket = bucket

    async def ensure_bucket(self) -> None:
        """Verify / create the bucket. Raises :class:`StorageUnavailableError` on failure."""
        await asyncio.to_thread(self._backend.ensure_bucket)

    async def put_object(
        self,
        prefix: str,
        name: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload *data* under ``{prefix}/{name}`` and return the full object path.

        Raises :class:`StorageUnavailableError` on connectivity failure.
        """
        if not isinstance(data, (bytes, bytearray)):
            data = data.read()
        raw: bytes = bytes(data)
        object_path = f"{prefix}/{name}"
        await asyncio.to_thread(self._backend.put_object, object_path, raw, content_type)
        logger.debug("Stored: bucket=%s path=%s size=%d", self._bucket, object_path, len(raw))
        return object_path

    async def get_object(self, path: str) -> bytes:
        """
        Retrieve raw bytes at *path*. Raises :class:`StorageUnavailableError` on failure.
        """
        data: bytes = await asyncio.to_thread(self._backend.get_object, path)
        logger.debug("Retrieved: bucket=%s path=%s size=%d", self._bucket, path, len(data))
        return data

    async def get_presigned_url(self, path: str, expiry_seconds: int = 3600) -> str:
        """
        Return a presigned/signed URL valid for *expiry_seconds* (default 1 hour).

        Works identically for both MinIO and Supabase S3 — both use the standard
        S3 presigned URL mechanism via the MinIO SDK.
        """
        url: str = await asyncio.to_thread(
            self._backend.get_presigned_url, path, expiry_seconds
        )
        logger.debug("Presigned URL for %s (expires %ds)", path, expiry_seconds)
        return url

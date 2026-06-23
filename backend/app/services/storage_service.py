"""
Object storage abstraction for TrafficVision AI.

Two storage backends are supported:

* **MinIO** (``STORAGE_BACKEND=minio``) — local dockerized MinIO for development,
  using the MinIO Python SDK.
* **Supabase S3** (``STORAGE_BACKEND=supabase``) — Supabase object storage in
  production, using boto3.  The MinIO SDK cannot be used here because it rejects
  endpoint URLs that contain a path component (e.g. ``/storage/v1/s3``), which
  Supabase requires.  boto3 accepts a full ``endpoint_url`` with a path.

:class:`StorageService` is the public async facade consumed by the rest of the app.

Custom exceptions
-----------------
* :class:`StorageUnavailableError` — raised for any connectivity-level failure.
"""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import timedelta
from typing import BinaryIO, Protocol

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
# Backend protocol (structural typing)
# ---------------------------------------------------------------------------


class StorageBackend(Protocol):
    _bucket: str

    def ensure_bucket(self) -> None: ...
    def put_object(self, object_path: str, data: bytes, content_type: str) -> None: ...
    def get_object(self, path: str) -> bytes: ...
    def get_presigned_url(self, path: str, expiry_seconds: int = 3600) -> str: ...


# ---------------------------------------------------------------------------
# MinIO helpers
# ---------------------------------------------------------------------------


def _is_minio_connectivity_error(exc: Exception) -> bool:
    from minio.error import S3Error
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
# MinioStorageBackend — local MinIO (development)
# ---------------------------------------------------------------------------


class MinioStorageBackend:
    """
    S3-compatible storage backend using the MinIO Python SDK.

    Use for local Docker MinIO only.  For Supabase use :class:`SupabaseS3Backend`.

    Parameters
    ----------
    endpoint:
        Host (+ optional port) without scheme, e.g. ``"localhost:9000"``.
    access_key / secret_key:
        MinIO credentials.
    bucket:
        Bucket name.
    secure:
        Use HTTPS when ``True``.
    public_endpoint:
        Optional separate host used only for generating presigned URLs.
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
        from minio import Minio

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
    def _url_client(self):
        return self._public_client or self._client

    def ensure_bucket(self) -> None:
        from minio.error import S3Error

        try:
            exists = self._client.bucket_exists(self._bucket)
        except (MaxRetryError, NewConnectionError, ConnectionError, ConnectionRefusedError) as exc:
            raise _wrap_connectivity(exc, "ensure_bucket") from exc
        except S3Error as exc:
            if _is_minio_connectivity_error(exc):
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
                elif _is_minio_connectivity_error(exc):
                    raise _wrap_connectivity(exc, "make_bucket") from exc
                else:
                    raise
        else:
            logger.debug("Bucket already exists: %s", self._bucket)

    def put_object(self, object_path: str, data: bytes, content_type: str) -> None:
        from minio.error import S3Error

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
            if _is_minio_connectivity_error(exc):
                raise _wrap_connectivity(exc, f"put_object({object_path})") from exc
            raise

    def get_object(self, path: str) -> bytes:
        from minio.error import S3Error

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
            if _is_minio_connectivity_error(exc):
                raise _wrap_connectivity(exc, f"get_object({path})") from exc
            raise

    def get_presigned_url(self, path: str, expiry_seconds: int = 3600) -> str:
        from minio.error import S3Error

        try:
            return self._url_client.presigned_get_object(
                self._bucket,
                path,
                expires=timedelta(seconds=expiry_seconds),
            )
        except (MaxRetryError, NewConnectionError, ConnectionError, ConnectionRefusedError) as exc:
            raise _wrap_connectivity(exc, f"get_presigned_url({path})") from exc
        except S3Error as exc:
            if _is_minio_connectivity_error(exc):
                raise _wrap_connectivity(exc, f"get_presigned_url({path})") from exc
            raise


# ---------------------------------------------------------------------------
# SupabaseS3Backend — Supabase S3-compatible storage (production)
#
# Uses boto3 because the MinIO SDK rejects endpoint URLs that contain a path
# component (e.g. /storage/v1/s3), which is required by Supabase.
# ---------------------------------------------------------------------------


class SupabaseS3Backend:
    """
    Supabase object storage backend using boto3 (AWS SDK).

    boto3 accepts a full ``endpoint_url`` including the ``/storage/v1/s3`` path
    that the Supabase S3-compatible API requires.

    Parameters
    ----------
    endpoint_url:
        Full HTTPS URL, e.g.
        ``"https://dvibhmdfprwxqjupoxfw.supabase.co/storage/v1/s3"``.
    access_key / secret_key:
        S3 Access Key ID and Secret from Supabase dashboard → Storage → S3 Access.
    region:
        Region shown in the S3 Access panel (e.g. ``"ap-south-1"``).
    bucket:
        Bucket name (must be pre-created in Supabase dashboard).
    """

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str,
        bucket: str,
    ) -> None:
        import boto3

        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._region = region
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        logger.info(
            "SupabaseS3Backend initialised (endpoint=%s, bucket=%s, region=%s)",
            endpoint_url,
            bucket,
            region,
        )

    def _wrap(self, exc: Exception, operation: str) -> StorageUnavailableError:
        msg = f"Supabase S3 unavailable during '{operation}': {type(exc).__name__}: {exc}"
        logger.error(msg)
        return StorageUnavailableError(msg, cause=exc)

    def ensure_bucket(self) -> None:
        """Verify the bucket is accessible. Supabase buckets are pre-created in the
        dashboard, so we just do a lightweight head_bucket check."""
        try:
            self._s3.head_bucket(Bucket=self._bucket)
            logger.debug("Bucket accessible: %s", self._bucket)
        except Exception as exc:
            from botocore.exceptions import ClientError, EndpointConnectionError, ConnectTimeoutError
            if isinstance(exc, (EndpointConnectionError, ConnectTimeoutError, ConnectionError)):
                raise self._wrap(exc, "ensure_bucket") from exc
            if isinstance(exc, ClientError):
                code = exc.response.get("Error", {}).get("Code", "")
                if code == "404":
                    raise StorageUnavailableError(
                        f"Bucket '{self._bucket}' not found in Supabase. "
                        "Create it in the Supabase dashboard → Storage.",
                        cause=exc,
                    ) from exc
                if code in ("403", "AccessDenied"):
                    raise StorageUnavailableError(
                        f"Access denied to bucket '{self._bucket}'. "
                        "Check your S3 Access Key credentials.",
                        cause=exc,
                    ) from exc
                raise self._wrap(exc, "ensure_bucket") from exc
            raise self._wrap(exc, "ensure_bucket") from exc

    def put_object(self, object_path: str, data: bytes, content_type: str) -> None:
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=object_path,
                Body=data,
                ContentType=content_type,
            )
        except Exception as exc:
            raise self._wrap(exc, f"put_object({object_path})") from exc

    def get_object(self, path: str) -> bytes:
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=path)
            return response["Body"].read()
        except Exception as exc:
            from botocore.exceptions import ClientError
            if isinstance(exc, ClientError):
                code = exc.response.get("Error", {}).get("Code", "")
                if code in ("404", "NoSuchKey"):
                    raise  # re-raise so callers can treat as "not found"
            raise self._wrap(exc, f"get_object({path})") from exc

    def get_presigned_url(self, path: str, expiry_seconds: int = 3600) -> str:
        try:
            return self._s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": path},
                ExpiresIn=expiry_seconds,
            )
        except Exception as exc:
            raise self._wrap(exc, f"get_presigned_url({path})") from exc


# ---------------------------------------------------------------------------
# StorageService — async facade
# ---------------------------------------------------------------------------


class StorageService:
    """
    Async-friendly facade over a storage backend (MinIO or Supabase S3).

    All blocking SDK calls are dispatched via :func:`asyncio.to_thread` so
    the FastAPI event loop stays responsive.

    Parameters
    ----------
    backend:
        A :class:`MinioStorageBackend` or :class:`SupabaseS3Backend` instance.
    bucket:
        Bucket name — stored for log messages and health-check access.
    """

    def __init__(self, backend: MinioStorageBackend | SupabaseS3Backend, bucket: str) -> None:
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
        Return a presigned URL valid for *expiry_seconds* (default 1 hour).
        """
        url: str = await asyncio.to_thread(
            self._backend.get_presigned_url, path, expiry_seconds
        )
        logger.debug("Presigned URL for %s (expires %ds)", path, expiry_seconds)
        return url

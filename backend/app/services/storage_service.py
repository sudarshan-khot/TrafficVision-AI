"""
MinIO object storage wrapper.

This module provides :class:`StorageService`, a thin async-friendly wrapper
around the synchronous MinIO Python client.  All blocking I/O is performed
via :func:`asyncio.to_thread` so the FastAPI event loop stays responsive.

Custom exceptions
-----------------
* :class:`StorageUnavailableError` — raised when the MinIO client raises a
  connection-level error (``urllib3.exceptions.MaxRetryError``,
  ``minio.error.S3Error`` with a network cause, ``ConnectionError``, etc.).
  Callers that need to map storage failures to HTTP 503 should catch this.
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
    """
    Raised when the MinIO Storage Service cannot be reached.

    Wraps lower-level network exceptions so callers only need to catch one
    exception type for availability failures.
    """

    def __init__(self, message: str = "Storage service unavailable", cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


# ---------------------------------------------------------------------------
# Helper — classify MinIO / urllib3 errors
# ---------------------------------------------------------------------------

def _is_connectivity_error(exc: Exception) -> bool:
    """Return True if *exc* represents a network / connectivity failure."""
    if isinstance(exc, (MaxRetryError, NewConnectionError, ConnectionError, ConnectionRefusedError)):
        return True
    if isinstance(exc, S3Error):
        # S3Error wraps lower-level errors; check the cause chain
        cause = exc.__cause__ or exc.__context__
        if cause is not None and isinstance(cause, (MaxRetryError, NewConnectionError, ConnectionError)):
            return True
        # MinIO also raises S3Error for "NoSuchBucket" etc.; those are NOT
        # connectivity errors — only treat connection-related codes as such.
        # We do NOT catch all S3Errors indiscriminately here.
    return False


def _wrap_connectivity(exc: Exception, operation: str) -> StorageUnavailableError:
    """Convert a low-level connectivity error to :class:`StorageUnavailableError`."""
    msg = f"Storage service unavailable during '{operation}': {exc}"
    logger.error(msg)
    return StorageUnavailableError(msg, cause=exc)


# ---------------------------------------------------------------------------
# StorageService
# ---------------------------------------------------------------------------


class StorageService:
    """
    Async-friendly wrapper around the MinIO Python SDK.

    Parameters
    ----------
    endpoint:
        MinIO server address in ``host:port`` form (e.g. ``"localhost:9000"``).
    access_key:
        MinIO access key / root user name.
    secret_key:
        MinIO secret key / root password.
    bucket:
        Name of the bucket to use for all operations.
    secure:
        If ``True``, connect over HTTPS; defaults to ``False`` (plain HTTP).
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
        public_endpoint: str | None = None,
        public_secure: bool | None = None,
    ) -> None:
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region="us-east-1",
        )
        if public_endpoint is None:
            self._public_client = None
        else:
            self._public_client = Minio(
                public_endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure if public_secure is None else public_secure,
                region="us-east-1",
            )
        self._bucket = bucket

    @property
    def public_client(self) -> Minio:
        """Return the MinIO client used for public presigned URLs."""
        if self._public_client is not None:
            return self._public_client
        return self._client

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def ensure_bucket(self) -> None:
        """
        Create the bucket if it does not already exist.

        Runs the blocking MinIO call in a thread-pool executor so as not to
        block the event loop.

        Raises
        ------
        StorageUnavailableError
            When the MinIO server is unreachable.
        """
        try:
            await asyncio.to_thread(self._sync_ensure_bucket)
        except StorageUnavailableError:
            raise
        except (MaxRetryError, NewConnectionError, ConnectionError, ConnectionRefusedError) as exc:
            raise _wrap_connectivity(exc, "ensure_bucket") from exc
        except S3Error as exc:
            if _is_connectivity_error(exc):
                raise _wrap_connectivity(exc, "ensure_bucket") from exc
            raise

    async def put_object(
        self,
        prefix: str,
        name: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload *data* to MinIO and return the full object path.

        Parameters
        ----------
        prefix:
            Folder prefix inside the bucket (e.g. ``"original"`` or
            ``"annotated"``).  A ``/`` separator is inserted automatically.
        name:
            Object filename (e.g. ``"abc123.jpg"``).
        data:
            Raw bytes or a file-like object open for reading.
        content_type:
            MIME type of the object (e.g. ``"image/jpeg"``).

        Returns
        -------
        str
            The full object path as stored in the bucket, e.g.
            ``"original/abc123.jpg"``.

        Raises
        ------
        StorageUnavailableError
            When the MinIO server is unreachable.
        """
        object_path = f"{prefix}/{name}"

        # Normalise data to bytes so we can compute the length reliably.
        if isinstance(data, (bytes, bytearray)):
            raw_bytes: bytes = bytes(data)
        else:
            raw_bytes = data.read()

        length = len(raw_bytes)
        buffer = io.BytesIO(raw_bytes)

        try:
            await asyncio.to_thread(
                self._client.put_object,
                self._bucket,
                object_path,
                buffer,
                length,
                content_type=content_type,
            )
        except (MaxRetryError, NewConnectionError, ConnectionError, ConnectionRefusedError) as exc:
            raise _wrap_connectivity(exc, f"put_object({object_path})") from exc
        except S3Error as exc:
            if _is_connectivity_error(exc):
                raise _wrap_connectivity(exc, f"put_object({object_path})") from exc
            raise

        logger.debug("Stored object: bucket=%s path=%s size=%d", self._bucket, object_path, length)
        return object_path

    async def get_object(self, path: str) -> bytes:
        """
        Retrieve the object at *path* from the bucket and return its contents.

        Parameters
        ----------
        path:
            Full object path inside the bucket (e.g.
            ``"original/abc123.jpg"``).

        Returns
        -------
        bytes
            The raw bytes of the stored object.

        Raises
        ------
        StorageUnavailableError
            When the MinIO server is unreachable.
        S3Error
            When the object does not exist (``NoSuchKey``), the bucket is
            missing, or any other non-connectivity S3 error occurs.
        """
        try:
            response = await asyncio.to_thread(
                self._client.get_object,
                self._bucket,
                path,
            )
            try:
                data = response.read()
            finally:
                response.close()
                response.release_conn()
        except (MaxRetryError, NewConnectionError, ConnectionError, ConnectionRefusedError) as exc:
            raise _wrap_connectivity(exc, f"get_object({path})") from exc
        except S3Error as exc:
            if _is_connectivity_error(exc):
                raise _wrap_connectivity(exc, f"get_object({path})") from exc
            raise

        logger.debug("Retrieved object: bucket=%s path=%s size=%d", self._bucket, path, len(data))
        return data

    async def get_presigned_url(self, path: str, expiry_seconds: int = 3600) -> str:
        """
        Generate a pre-signed URL for temporary public access to an object.

        Parameters
        ----------
        path:
            Full object path inside the bucket (e.g.
            ``"annotated/abc123_annotated.jpg"``).
        expiry_seconds:
            Number of seconds the URL will remain valid.  Defaults to
            ``3600`` (1 hour) as required by Requirement 4.3.

        Returns
        -------
        str
            A pre-signed HTTPS/HTTP URL string.

        Raises
        ------
        StorageUnavailableError
            When the MinIO server is unreachable.
        S3Error
            For other non-connectivity S3 errors.
        """
        expiry = timedelta(seconds=expiry_seconds)
        try:
            url: str = await asyncio.to_thread(
                self.public_client.presigned_get_object,
                self._bucket,
                path,
                expires=expiry,
            )
        except (MaxRetryError, NewConnectionError, ConnectionError, ConnectionRefusedError) as exc:
            raise _wrap_connectivity(exc, f"get_presigned_url({path})") from exc
        except S3Error as exc:
            if _is_connectivity_error(exc):
                raise _wrap_connectivity(exc, f"get_presigned_url({path})") from exc
            raise

        logger.debug("Generated presigned URL for: %s (expires in %ds)", path, expiry_seconds)
        return url

    # ------------------------------------------------------------------
    # Private synchronous helpers (run inside thread-pool)
    # ------------------------------------------------------------------

    def _sync_ensure_bucket(self) -> None:
        """Create the bucket if it does not already exist (synchronous)."""
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
                logger.info("Created MinIO bucket: %s", self._bucket)
            except (MaxRetryError, NewConnectionError, ConnectionError, ConnectionRefusedError) as exc:
                raise _wrap_connectivity(exc, "make_bucket") from exc
            except S3Error as exc:
                # BucketAlreadyOwnedByYou — race condition in multi-process startup; safe to ignore
                if exc.code == "BucketAlreadyOwnedByYou":
                    logger.debug("Bucket %s already owned; ignoring race condition", self._bucket)
                elif _is_connectivity_error(exc):
                    raise _wrap_connectivity(exc, "make_bucket") from exc
                else:
                    raise
        else:
            logger.debug("MinIO bucket already exists: %s", self._bucket)

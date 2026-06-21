"""
Image upload validation and storage.

Requirements: 1.1, 1.3, 1.4, 1.5
"""
from __future__ import annotations

from fastapi import UploadFile

from app.services.storage_service import StorageService, StorageUnavailableError

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png"})


class FileTooLargeError(Exception):
    """Raised when an uploaded file exceeds the size limit."""


class UnsupportedMediaTypeError(Exception):
    """Raised when an uploaded file is not JPEG or PNG."""


class ImageService:
    """Validate uploads and store originals in MinIO."""

    def __init__(self, storage_service: StorageService) -> None:
        self._storage = storage_service

    async def validate_upload(self, file: UploadFile) -> None:
        """Enforce size and MIME type constraints."""
        content_type = (file.content_type or "").lower()
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise UnsupportedMediaTypeError(
                "Unsupported media type. Only JPEG and PNG are accepted"
            )

        data = await file.read()
        await file.seek(0)
        if len(data) > MAX_UPLOAD_BYTES:
            raise FileTooLargeError("File size exceeds 20 MB limit")

    async def store_original(
        self,
        image_id: str,
        file_bytes: bytes,
        content_type: str,
    ) -> str:
        """Store the original image under ``original/`` in MinIO."""
        extension = "png" if content_type == "image/png" else "jpg"
        try:
            return await self._storage.put_object(
                prefix="original",
                name=f"{image_id}.{extension}",
                data=file_bytes,
                content_type=content_type,
            )
        except StorageUnavailableError:
            raise

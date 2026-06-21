"""
Evidence image upload helper.

Requirements: 2.7, 2.8, 8.3, 8.5
"""
from __future__ import annotations

import logging

from app.services.storage_service import StorageService, StorageUnavailableError

logger = logging.getLogger(__name__)


class EvidenceUploader:
    """Upload annotated images and plate crops to MinIO."""

    def __init__(self, storage_service: StorageService | None) -> None:
        self._storage = storage_service

    async def upload(
        self,
        image_id: str,
        annotated_bytes: bytes,
        crops: dict[str, bytes],
    ) -> tuple[str | None, dict[str, str]]:
        """
        Store annotated image and plate crops in MinIO.

        Returns
        -------
        tuple[str | None, dict[str, str]]
            Annotated object path (or ``None`` on failure) and a dict mapping
            crop keys to their MinIO object paths.
        """
        if self._storage is None:
            logger.warning("Storage unavailable — skipping evidence upload for %s", image_id)
            return None, {}

        annotated_path: str | None = None
        crop_paths: dict[str, str] = {}

        try:
            annotated_path = await self._storage.put_object(
                prefix="annotated",
                name=f"{image_id}_annotated.jpg",
                data=annotated_bytes,
                content_type="image/jpeg",
            )
        except StorageUnavailableError as exc:
            logger.warning("Failed to upload annotated image for %s: %s", image_id, exc)
            return None, {}

        for key, crop_bytes in crops.items():
            try:
                path = await self._storage.put_object(
                    prefix="crops",
                    name=f"{image_id}_plate_{key}.jpg",
                    data=crop_bytes,
                    content_type="image/jpeg",
                )
                crop_paths[key] = path
            except StorageUnavailableError as exc:
                logger.warning(
                    "Failed to upload plate crop %s for %s: %s",
                    key,
                    image_id,
                    exc,
                )

        return annotated_path, crop_paths

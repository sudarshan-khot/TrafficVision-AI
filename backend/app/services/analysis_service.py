"""
End-to-end ML analysis orchestration.

Requirements: 2.1–2.8
"""
from __future__ import annotations

import io
import logging
import time
from typing import TYPE_CHECKING, Any

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Vehicle
from app.detection.models import DetectedObject
from app.evidence.generator import EvidenceGenerator
from app.evidence.uploader import EvidenceUploader
from app.services.storage_service import StorageService
from app.services.violation_service import ViolationService
from app.violation_engine.engine import ViolationEngine

if TYPE_CHECKING:
    from app.detection.detector import DetectionService
    from app.ocr.ocr_pipeline import OCRPipeline

logger = logging.getLogger(__name__)

_VEHICLE_CLASSES = frozenset({"motorcycle", "car", "truck", "bus"})


class AnalysisService:
    """Coordinate detection, OCR, violation evaluation, and persistence."""

    async def run_analysis(
        self,
        image_id: str,
        db: AsyncSession,
        storage: StorageService,
        detector: Any,
        ocr: Any,
        violation_engine: ViolationEngine,
        evidence_gen: EvidenceGenerator,
        evidence_uploader: EvidenceUploader,
        original_object_path: str | None = None,
    ) -> dict:
        """
        Execute the full ML pipeline for one uploaded image.

        Returns a response dict with violations, vehicles, and processing time.
        """
        start = time.perf_counter()

        object_path = original_object_path or await self._resolve_original_path(
            storage, image_id
        )
        image_bytes = await storage.get_object(object_path)

        detection = detector.detect(image_bytes, image_id=image_id)
        plate_text_by_vehicle, plate_crops = await self._read_plates_and_crops(image_bytes, detection.objects, ocr)

        violations = violation_engine.evaluate(detection)
        for violation in violations:
            if violation.vehicle_id and violation.vehicle_id in plate_text_by_vehicle:
                violation.plate_number = plate_text_by_vehicle[violation.vehicle_id]

        vehicle_rows: list[Vehicle] = []
        violation_service = ViolationService(db)

        vehicle_objects = [
            obj for obj in detection.objects if obj.cls in _VEHICLE_CLASSES
        ]
        for obj in vehicle_objects:
            plate_number = plate_text_by_vehicle.get(obj.id)
            vehicle = await violation_service.create_vehicle(
                image_id=image_id,
                vehicle_class=obj.cls,
                bounding_box=obj.bounding_box.model_dump(),
                plate_number=plate_number,
                vehicle_id=obj.id,
            )
            vehicle_rows.append(vehicle)

        annotated_bytes = evidence_gen.generate(
            image_bytes,
            violations,
            vehicles=vehicle_rows,
        )
        annotated_path, _crop_paths = await evidence_uploader.upload(
            image_id,
            annotated_bytes,
            plate_crops,
        )

        persisted_violations = []
        for violation in violations:
            db_violation = await violation_service.create_violation(
                image_id=image_id,
                violation_type=violation.type.value,
                confidence=violation.confidence,
                bounding_box=violation.bounding_box.model_dump(),
                vehicle_id=violation.vehicle_id,
                plate_number=violation.plate_number,
                annotated_image_path=annotated_path,
            )
            persisted_violations.append(db_violation)

        await db.commit()

        annotated_image_url = None
        if annotated_path and storage is not None:
            annotated_image_url = await storage.get_presigned_url(
                annotated_path,
                expiry_seconds=3600,
            )

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return {
            "image_id": image_id,
            "annotated_image_url": annotated_image_url,
            "violations": [
                {
                    "id": v.id,
                    "violation_type": v.violation_type,
                    "confidence": v.confidence,
                    "bounding_box": v.bounding_box,
                    "plate_number": v.plate_number,
                    "annotated_image_path": v.annotated_image_path,
                }
                for v in persisted_violations
            ],
            "vehicles": [
                {
                    "id": v.id,
                    "vehicle_class": v.vehicle_class,
                    "bounding_box": v.bounding_box,
                    "plate_number": v.plate_number,
                }
                for v in vehicle_rows
            ],
            "processing_time_ms": elapsed_ms,
        }

    async def _resolve_original_path(self, storage: StorageService, image_id: str) -> str:
        for ext in ("jpg", "png"):
            path = f"original/{image_id}.{ext}"
            try:
                await storage.get_object(path)
                return path
            except Exception:  # noqa: BLE001
                continue
        raise FileNotFoundError(f"Image not found: {image_id}")

    async def _read_plates_and_crops(
        self,
        image_bytes: bytes,
        objects: list[DetectedObject],
        ocr: OCRPipeline,
    ) -> tuple[dict[str, str], dict[str, bytes]]:
        """OCR vehicle crops and map vehicle IDs to plate text and crops."""
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        plate_text_by_vehicle: dict[str, str] = {}
        plate_crops: dict[str, bytes] = {}

        number_plates = [o for o in objects if o.cls == "number_plate"]

        for obj in objects:
            if obj.cls not in _VEHICLE_CLASSES:
                continue

            # Try to find an overlapping number plate bounding box
            associated_plate = None
            best_overlap = 0.0
            for plate in number_plates:
                ix1 = max(obj.bounding_box.x1, plate.bounding_box.x1)
                iy1 = max(obj.bounding_box.y1, plate.bounding_box.y1)
                ix2 = min(obj.bounding_box.x2, plate.bounding_box.x2)
                iy2 = min(obj.bounding_box.y2, plate.bounding_box.y2)

                if ix2 > ix1 and iy2 > iy1:
                    inter_area = (ix2 - ix1) * (iy2 - iy1)
                    plate_area = (plate.bounding_box.x2 - plate.bounding_box.x1) * (
                        plate.bounding_box.y2 - plate.bounding_box.y1
                    )
                    overlap = inter_area / plate_area if plate_area > 0 else 0.0
                    if overlap > 0.7 and overlap > best_overlap:
                        best_overlap = overlap
                        associated_plate = plate

            success = False
            if associated_plate is not None:
                try:
                    px1, py1, px2, py2 = (
                        associated_plate.bounding_box.x1,
                        associated_plate.bounding_box.y1,
                        associated_plate.bounding_box.x2,
                        associated_plate.bounding_box.y2,
                    )
                    w, h = image.size
                    pad_x = int((px2 - px1) * 0.05)
                    pad_y = int((py2 - py1) * 0.05)
                    crop_box = (
                        max(0, int(px1) - pad_x),
                        max(0, int(py1) - pad_y),
                        min(w, int(px2) + pad_x),
                        min(h, int(py2) + pad_y),
                    )
                    plate_crop = image.crop(crop_box)
                    buf = io.BytesIO()
                    plate_crop.save(buf, format="JPEG")
                    plate_crop_bytes = buf.getvalue()

                    # Enhance using Real-ESRGAN and read
                    enhanced_bytes = ocr.enhance_crop(plate_crop_bytes)
                    plate_text = ocr.read_plate(enhanced_bytes, enhance=False)
                    if plate_text:
                        plate_text_by_vehicle[obj.id] = plate_text
                        plate_crops[obj.id] = enhanced_bytes
                        success = True
                except Exception as exc:
                    logger.warning("Failed to enhance and read plate: %s", exc)

            if success:
                continue

            # Fallback to OCR pipeline's internal detection on vehicle crop
            crop = image.crop(
                (
                    obj.bounding_box.x1,
                    obj.bounding_box.y1,
                    obj.bounding_box.x2,
                    obj.bounding_box.y2,
                )
            )
            buf = io.BytesIO()
            crop.save(buf, format="JPEG")
            
            plate_text, sub_crop_bytes = ocr.read_plate_with_crop(buf.getvalue())
            if plate_text:
                plate_text_by_vehicle[obj.id] = plate_text
                if sub_crop_bytes:
                    plate_crops[obj.id] = sub_crop_bytes

        return plate_text_by_vehicle, plate_crops

    @staticmethod
    def _build_plate_crops(
        image_bytes: bytes,
        objects: list[DetectedObject],
    ) -> dict[str, bytes]:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        crops: dict[str, bytes] = {}
        index = 0
        for obj in objects:
            if obj.cls != "number_plate":
                continue
            crop = image.crop(
                (
                    obj.bounding_box.x1,
                    obj.bounding_box.y1,
                    obj.bounding_box.x2,
                    obj.bounding_box.y2,
                )
            )
            buf = io.BytesIO()
            crop.save(buf, format="JPEG")
            crops[str(index)] = buf.getvalue()
            index += 1
        return crops


analysis_service = AnalysisService()

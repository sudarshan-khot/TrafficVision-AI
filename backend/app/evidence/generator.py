"""
Annotated evidence image generation.

Requirements: 8.1, 8.2, 8.4
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont

from app.database.models import Vehicle
from app.violation_engine.types import ViolationInstance, ViolationType

# Distinct colours per violation type (RGB).
_VIOLATION_COLOURS: dict[ViolationType, tuple[int, int, int]] = {
    ViolationType.HELMET_NON_COMPLIANCE: (255, 64, 64),
    ViolationType.TRIPLE_RIDING: (255, 165, 0),
    ViolationType.WRONG_SIDE_DRIVING: (128, 0, 255),
    ViolationType.STOP_LINE_VIOLATION: (255, 255, 0),
    ViolationType.ILLEGAL_PARKING: (0, 191, 255),
}


class EvidenceGenerator:
    """Draw violation annotations onto an image and return JPEG bytes."""

    def generate(
        self,
        image_bytes: bytes,
        violations: list[ViolationInstance],
        vehicles: list[Vehicle] | None = None,
    ) -> bytes:
        """
        Render bounding boxes and labels for each violation and vehicle.

        Always returns JPEG bytes regardless of the input image format.
        """
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Draw vehicle classification boxes first so violation boxes draw on top
        if vehicles:
            for vehicle in vehicles:
                cls_name = vehicle.vehicle_class.lower()
                if cls_name == "car":
                    colour = (46, 204, 113)  # Emerald Green
                elif cls_name == "motorcycle":
                    colour = (52, 152, 219)  # Cyan Blue
                elif cls_name == "bus":
                    colour = (241, 196, 15)   # Amber Yellow
                elif cls_name == "truck":
                    colour = (155, 89, 182)  # Purple
                else:
                    colour = (127, 140, 141)  # Gray

                box = vehicle.bounding_box
                x1 = box.get("x1", 0) if isinstance(box, dict) else getattr(box, "x1", 0)
                y1 = box.get("y1", 0) if isinstance(box, dict) else getattr(box, "y1", 0)
                x2 = box.get("x2", 0) if isinstance(box, dict) else getattr(box, "x2", 0)
                y2 = box.get("y2", 0) if isinstance(box, dict) else getattr(box, "y2", 0)

                draw.rectangle(
                    [(x1, y1), (x2, y2)],
                    outline=colour,
                    width=2,
                )

                label = f"{vehicle.vehicle_class.capitalize()}"
                if vehicle.plate_number:
                    label += f" | {vehicle.plate_number}"
                text_y = max(0, y1 - 14)
                draw.text((x1, text_y), label, fill=colour, font=font)

        for violation in violations:
            colour = _VIOLATION_COLOURS.get(violation.type, (255, 0, 0))
            box = violation.bounding_box
            draw.rectangle(
                [(box.x1, box.y1), (box.x2, box.y2)],
                outline=colour,
                width=3,
            )

            confidence_text = f"{violation.confidence:.2f}"
            label_parts = [
                violation.type.value,
                confidence_text,
            ]
            if violation.plate_number:
                label_parts.append(violation.plate_number)
            label_parts.append(timestamp)
            label = " | ".join(label_parts)

            text_y = max(0, box.y1 - 14)
            draw.text((box.x1, text_y), label, fill=colour, font=font)

        output = io.BytesIO()
        image.save(output, format="JPEG", quality=90)
        return output.getvalue()

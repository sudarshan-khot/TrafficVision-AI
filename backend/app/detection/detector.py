"""
YOLOv8m-based detection service for TrafficVision AI.

Loads ``yolov8m.pt`` and ``helmet_detection.pt`` once at instantiation and
exposes :meth:`DetectionService.detect` for per-image inference.

Requirements: 2.1, 7.1, 7.2, 7.3, 7.5
"""
from __future__ import annotations

import io
import logging
import sys
import uuid
from pathlib import Path

from PIL import Image
import json
import numpy as np

try:
    from ultralytics import YOLO
    has_ultralytics = True
except ImportError:
    YOLO = None
    has_ultralytics = False

try:
    import onnxruntime as ort
    has_ort = True
except ImportError:
    ort = None
    has_ort = False

from app.detection.models import BoundingBox, DetectedObject, DetectionResult
from app.detection.preprocessor import preprocess

logger = logging.getLogger(__name__)

# COCO / domain classes retained from the base detection model.
_VEHICLE_CLASSES: frozenset[str] = frozenset({"motorcycle", "car", "truck", "bus"})
_DETECTION_CLASSES: frozenset[str] = _VEHICLE_CLASSES | frozenset({"person", "number_plate"})

# Helmet model class labels (fine-tuned YOLOv8m).
_HELMET_POSITIVE: frozenset[str] = frozenset({"with_helmet", "with helmet"})
_HELMET_NEGATIVE: frozenset[str] = frozenset({"without_helmet", "without helmet"})

_INPUT_SIZE = 640


def _require_model(path: Path, label: str) -> None:
    """Exit the process if a required model file is missing."""
    if not path.is_file():
        msg = (
            f"Required model file not found: {path.resolve()}\n"
            f"Place {path.name} in the configured MODEL_DIR before starting the backend."
        )
        logger.error(msg)
        sys.exit(1)


def _iou(a: BoundingBox, b: BoundingBox) -> float:
    """Compute intersection-over-union for two axis-aligned boxes."""
    x_left = max(a.x1, b.x1)
    y_top = max(a.y1, b.y1)
    x_right = min(a.x2, b.x2)
    y_bottom = min(a.y2, b.y2)

    if x_right <= x_left or y_bottom <= y_top:
        return 0.0

    intersection = (x_right - x_left) * (y_bottom - y_top)
    area_a = max(0, a.x2 - a.x1) * max(0, a.y2 - a.y1)
    area_b = max(0, b.x2 - b.x1) * max(0, b.y2 - b.y1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _center_in_box(cx: float, cy: float, box: BoundingBox) -> bool:
    """Return True when point (cx, cy) lies inside *box*."""
    return box.x1 <= cx <= box.x2 and box.y1 <= cy <= box.y2


def _scale_box(x1: float, y1: float, x2: float, y2: float, sx: float, sy: float) -> BoundingBox:
    """Scale a box from preprocessed coordinates back to original image space."""
    return BoundingBox(
        x1=max(0, int(x1 * sx)),
        y1=max(0, int(y1 * sy)),
        x2=max(0, int(x2 * sx)),
        y2=max(0, int(y2 * sy)),
    )


def _val(x):
    """Return the raw scalar value from a PyTorch tensor or raw numeric type."""
    return x.item() if hasattr(x, "item") else x


class DetectionService:
    """
    Dual-mode inference service supporting ONNX Runtime (low-memory) and PyTorch.

    Model weights are loaded exactly once in ``__init__`` and kept in memory
    for the lifetime of the process.
    """

    def __init__(self, model_dir: str = "trained_models", yolo_session=None, helmet_session=None) -> None:
        model_path = Path(model_dir)
        self.use_onnx = False

        # Check for ONNX models first (highly preferred in production for memory reasons)
        yolov8_onnx_path = model_path / "yolov8m.onnx"
        if not yolov8_onnx_path.is_file():
            yolov8_onnx_path = model_path / "yolov8n.onnx"
        helmet_onnx_path = model_path / "yolo26n.onnx"

        yolo_names_path = yolov8_onnx_path.with_suffix(".names.json")
        helmet_names_path = helmet_onnx_path.with_suffix(".names.json")

        if has_ort and yolov8_onnx_path.is_file() and helmet_onnx_path.is_file() and yolo_names_path.is_file() and helmet_names_path.is_file():
            self.use_onnx = True
            logger.info("Initializing ONNX models for Inference: %s and %s", yolov8_onnx_path.name, helmet_onnx_path.name)
            
            if yolo_session and helmet_session:
                self._yolo_session = yolo_session
                self._helmet_session = helmet_session
                logger.info("Using globally pre-initialized ONNX sessions.")
            else:
                self._yolo_session = ort.InferenceSession(str(yolov8_onnx_path), providers=["CPUExecutionProvider"])
                self._helmet_session = ort.InferenceSession(str(helmet_onnx_path), providers=["CPUExecutionProvider"])

            with open(yolo_names_path, "r", encoding="utf-8") as f:
                self.yolo_names = {int(k): v for k, v in json.load(f).items()}
            with open(helmet_names_path, "r", encoding="utf-8") as f:
                self.helmet_names = {int(k): v for k, v in json.load(f).items()}

            logger.info("ONNX sessions successfully initialized.")
        else:
            if not has_ultralytics:
                raise ImportError(
                    "ONNX Runtime or ONNX model files are missing, and 'ultralytics' (PyTorch) is not installed. "
                    "Please install either 'onnxruntime' with exported ONNX models, or 'ultralytics'."
                )

            yolov8_path = model_path / "yolov8m.pt"
            if not yolov8_path.is_file():
                yolov8_path = model_path / "yolov8n.pt"
            helmet_path = model_path / "yolo26n.pt"

            _require_model(yolov8_path, yolov8_path.name)
            _require_model(helmet_path, "yolo26n.pt")

            self._yolo = YOLO(str(yolov8_path))
            self._helmet_model = YOLO(str(helmet_path))
            self.yolo_names = self._yolo.names
            self.helmet_names = self._helmet_model.names
            logger.info("DetectionService initialized using PyTorch/Ultralytics (yolo=%s, helmet=%s)", yolov8_path.name, helmet_path.name)

    def _run_onnx_inference(
        self,
        session: ort.InferenceSession,
        img_np: np.ndarray,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
    ) -> list[tuple[list[float], float, int]]:
        """Run custom ONNX inference with NMS post-processing using NumPy and OpenCV."""
        import cv2

        h, w = img_np.shape[:2]
        if (h, w) != (640, 640):
            img_resized = cv2.resize(img_np, (640, 640), interpolation=cv2.INTER_LINEAR)
        else:
            img_resized = img_np

        # Preprocessing: convert to float32, normalize, transpose to CHW, add batch dimension
        img_input = img_resized.astype(np.float32) / 255.0
        img_input = np.transpose(img_input, (2, 0, 1))
        img_input = np.expand_dims(img_input, axis=0)
        img_input = np.ascontiguousarray(img_input)

        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: img_input})
        output_tensor = outputs[0]  # Shape: (1, 4 + num_classes, 8400)

        # Transpose outputs to shape (8400, 4 + num_classes)
        output = output_tensor[0].T
        boxes = output[:, :4]  # [cx, cy, w, h]
        scores = output[:, 4:]  # class probabilities

        class_ids = np.argmax(scores, axis=1)
        confidences = np.max(scores, axis=1)

        # Filter detections by confidence
        mask = confidences > conf_threshold
        boxes = boxes[mask]
        confidences = confidences[mask]
        class_ids = class_ids[mask]

        if len(boxes) == 0:
            return []

        # Convert box format from [cx, cy, w, h] to [x1, y1, w, h] for NMS
        x_center = boxes[:, 0]
        y_center = boxes[:, 1]
        bw = boxes[:, 2]
        bh = boxes[:, 3]

        bx1 = x_center - bw / 2
        by1 = y_center - bh / 2

        nms_boxes = np.stack([bx1, by1, bw, bh], axis=1).tolist()
        nms_confidences = confidences.tolist()

        indices = cv2.dnn.NMSBoxes(
            nms_boxes,
            nms_confidences,
            score_threshold=conf_threshold,
            nms_threshold=iou_threshold,
        )

        results = []
        if len(indices) > 0:
            flat_indices = np.array(indices).flatten()
            for idx in flat_indices:
                x1_640, y1_640, w_640, h_640 = nms_boxes[idx]
                x2_640 = x1_640 + w_640
                y2_640 = y1_640 + h_640

                # Ensure dimensions are strictly inside bounds
                x1_640 = max(0.0, min(640.0, x1_640))
                y1_640 = max(0.0, min(640.0, y1_640))
                x2_640 = max(0.0, min(640.0, x2_640))
                y2_640 = max(0.0, min(640.0, y2_640))

                results.append(([x1_640, y1_640, x2_640, y2_640], nms_confidences[idx], class_ids[idx]))

        return results

    def detect(self, image_bytes: bytes, image_id: str) -> DetectionResult:
        """
        Run YOLO inference (ONNX or PyTorch) on *image_bytes* and return detections.
        """
        logger.info("[DetectionService] detect() called for image_id: %s, size: %d bytes", image_id, len(image_bytes))
        original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        orig_w, orig_h = original.size
        sx = orig_w / _INPUT_SIZE
        sy = orig_h / _INPUT_SIZE

        # Use getattr to prevent crashes if custom unit testing instantiates this via __new__
        if getattr(self, "use_onnx", False):
            # ─────────────────────────────────────────────────────────
            # ONNX Runtime Inference Path
            # ─────────────────────────────────────────────────────────
            import cv2
            img_np = np.array(original)

            # Model 1: Vehicle and license plate detector
            yolo_results = self._run_onnx_inference(self._yolo_session, img_np, conf_threshold=0.25)

            objects: list[DetectedObject] = []
            motorcycles: list[DetectedObject] = []
            vehicles: list[DetectedObject] = []

            logger.info("[DetectionService] ONNX Model 1 found %d filtered boxes", len(yolo_results))
            for box_640, conf, cls_id in yolo_results:
                cls_name = str(self.yolo_names.get(cls_id, str(cls_id))).lower().replace(" ", "_")
                logger.info("[DetectionService] ONNX Model 1 box: class_name=%s, conf=%.3f", cls_name, conf)
                if cls_name not in _DETECTION_CLASSES:
                    continue

                bbox = _scale_box(box_640[0], box_640[1], box_640[2], box_640[3], sx, sy)
                obj_id = str(uuid.uuid4())
                attributes: dict = {}

                if cls_name == "motorcycle":
                    attributes["rider_count"] = 0

                detected = DetectedObject(
                    id=obj_id,
                    cls=cls_name,
                    confidence=conf,
                    bounding_box=bbox,
                    attributes=attributes,
                )

                if cls_name == "motorcycle":
                    motorcycles.append(detected)
                    objects.append(detected)
                elif cls_name in _VEHICLE_CLASSES:
                    vehicles.append(detected)
                    objects.append(detected)
                elif cls_name == "person":
                    detected.attributes["helmet"] = None
                    objects.append(detected)
                elif cls_name == "number_plate":
                    objects.append(detected)

            logger.info("[DetectionService] ONNX Filtered objects: total=%d, motorcycles=%d", len(objects), len(motorcycles))

            # Model 2: Secondary helmet detector mapping
            names_m2 = self.helmet_names
            has_helmet_classes = False
            with_helmet_ids = set()
            without_helmet_ids = set()
            person_ids = set()

            for cid, cname in names_m2.items():
                cname_lower = cname.lower()
                if any(w in cname_lower for w in ["without_helmet", "without helmet", "no_helmet", "no helmet", "unhelmeted", "no-helmet"]):
                    without_helmet_ids.add(cid)
                    has_helmet_classes = True
                elif any(w in cname_lower for w in ["with_helmet", "with helmet", "helmeted", "helmet"]):
                    if "without" not in cname_lower:
                        with_helmet_ids.add(cid)
                        has_helmet_classes = True
                elif any(w in cname_lower for w in ["person", "rider", "passenger"]):
                    person_ids.add(cid)

            logger.info("[DetectionService] ONNX Model 2 has_helmet_classes=%s, person_ids=%s", has_helmet_classes, person_ids)

            # Evaluate riders/helmets on cropped motorcycle images
            for moto in motorcycles:
                m_box = moto.bounding_box
                crop = original.crop((m_box.x1, m_box.y1, m_box.x2, m_box.y2))
                if crop.width == 0 or crop.height == 0:
                    continue

                crop_np = np.array(crop)
                m2_results = self._run_onnx_inference(self._helmet_session, crop_np, conf_threshold=0.25)

                riders_count = 0
                logger.info("[DetectionService] ONNX Model 2 found %d boxes inside crop", len(m2_results))
                for box_640_c, conf_c, cls_id_c in m2_results:
                    is_rider = False
                    helmet_status = None

                    if has_helmet_classes:
                        if cls_id_c in without_helmet_ids:
                            is_rider = True
                            helmet_status = False
                        elif cls_id_c in with_helmet_ids:
                            is_rider = True
                            helmet_status = True
                        elif cls_id_c in person_ids:
                            is_rider = True
                            helmet_status = True
                    else:
                        if cls_id_c in person_ids or cls_id_c == 0:
                            is_rider = True
                            helmet_status = False

                    logger.info("[DetectionService] ONNX Model 2 box: class_id=%d, class_name=%s, conf=%.3f, is_rider=%s, helmet_status=%s",
                                cls_id_c, names_m2.get(cls_id_c, str(cls_id_c)), conf_c, is_rider, helmet_status)

                    if is_rider:
                        riders_count += 1
                        cx1, cy1, cx2, cy2 = box_640_c
                        csx = crop.width / 640.0
                        csy = crop.height / 640.0

                        x1_orig = m_box.x1 + int(cx1 * csx)
                        y1_orig = m_box.y1 + int(cy1 * csy)
                        x2_orig = m_box.x1 + int(cx2 * csx)
                        y2_orig = m_box.y1 + int(cy2 * csy)

                        rider_obj = DetectedObject(
                            id=str(uuid.uuid4()),
                            cls="person",
                            confidence=conf_c,
                            bounding_box=BoundingBox(
                                x1=x1_orig,
                                y1=y1_orig,
                                x2=x2_orig,
                                y2=y2_orig,
                            ),
                            attributes={"helmet": helmet_status},
                            associated_vehicle_id=moto.id,
                        )
                        objects.append(rider_obj)

                moto.attributes["rider_count"] = riders_count

            return DetectionResult(
                image_id=image_id,
                objects=objects,
                motorcycles=motorcycles,
            )
        else:
            # ─────────────────────────────────────────────────────────
            # PyTorch / Ultralytics Fallback Path
            # ─────────────────────────────────────────────────────────
            array = preprocess(image_bytes)
            yolo_results = self._yolo.predict(
                array,
                verbose=False,
                conf=0.25,
            )

            objects: list[DetectedObject] = []
            motorcycles: list[DetectedObject] = []
            vehicles: list[DetectedObject] = []

            if yolo_results and yolo_results[0].boxes is not None:
                names = yolo_results[0].names
                logger.info("[DetectionService] Model 1 found %d raw boxes", len(yolo_results[0].boxes))
                for box_tensor, conf_tensor, cls_tensor in zip(
                    yolo_results[0].boxes.xyxy,
                    yolo_results[0].boxes.conf,
                    yolo_results[0].boxes.cls,
                ):
                    cls_id = int(_val(cls_tensor))
                    cls_name = str(names.get(cls_id, str(cls_id))).lower().replace(" ", "_")
                    logger.info("[DetectionService] Model 1 raw box: class_name=%s, conf=%.3f", cls_name, float(_val(conf_tensor)))
                    if cls_name not in _DETECTION_CLASSES:
                        continue

                    bbox = _scale_box(
                        _val(box_tensor[0]),
                        _val(box_tensor[1]),
                        _val(box_tensor[2]),
                        _val(box_tensor[3]),
                        sx,
                        sy,
                    )
                    obj_id = str(uuid.uuid4())
                    attributes: dict = {}

                    if cls_name == "motorcycle":
                        attributes["rider_count"] = 0

                    detected = DetectedObject(
                        id=obj_id,
                        cls=cls_name,
                        confidence=float(_val(conf_tensor)),
                        bounding_box=bbox,
                        attributes=attributes,
                    )

                    if cls_name == "motorcycle":
                        motorcycles.append(detected)
                        objects.append(detected)
                    elif cls_name in _VEHICLE_CLASSES:
                        vehicles.append(detected)
                        objects.append(detected)
                    elif cls_name == "person":
                        detected.attributes["helmet"] = None
                        objects.append(detected)
                    elif cls_name == "number_plate":
                        objects.append(detected)

            logger.info("[DetectionService] Filtered objects: total=%d, motorcycles=%d", len(objects), len(motorcycles))

            names_m2 = self._helmet_model.names
            has_helmet_classes = False
            with_helmet_ids = set()
            without_helmet_ids = set()
            person_ids = set()

            for cid, cname in names_m2.items():
                cname_lower = cname.lower()
                if any(w in cname_lower for w in ["without_helmet", "without helmet", "no_helmet", "no helmet", "unhelmeted", "no-helmet"]):
                    without_helmet_ids.add(cid)
                    has_helmet_classes = True
                elif any(w in cname_lower for w in ["with_helmet", "with helmet", "helmeted", "helmet"]):
                    if "without" not in cname_lower:
                        with_helmet_ids.add(cid)
                        has_helmet_classes = True
                elif any(w in cname_lower for w in ["person", "rider", "passenger"]):
                    person_ids.add(cid)

            logger.info("[DetectionService] Model 2 has_helmet_classes=%s, person_ids=%s", has_helmet_classes, person_ids)

            for moto in motorcycles:
                m_box = moto.bounding_box
                crop = original.crop((m_box.x1, m_box.y1, m_box.x2, m_box.y2))
                if crop.width == 0 or crop.height == 0:
                    logger.info("[DetectionService] Empty crop for motorcycle %s", moto.id)
                    continue

                logger.info("[DetectionService] Motorcycle %s crop size: %dx%d", moto.id, crop.width, crop.height)
                m2_results = self._helmet_model.predict(
                    crop,
                    verbose=False,
                    conf=0.25,
                )

                riders_count = 0
                if m2_results and m2_results[0].boxes is not None:
                    logger.info("[DetectionService] Model 2 found %d raw boxes inside crop", len(m2_results[0].boxes))
                    for box_tensor, conf_tensor, cls_tensor in zip(
                        m2_results[0].boxes.xyxy,
                        m2_results[0].boxes.conf,
                        m2_results[0].boxes.cls,
                    ):
                        m2_cls_id = int(_val(cls_tensor))
                        m2_cls_name = names_m2.get(m2_cls_id, str(m2_cls_id))
                        is_rider = False
                        helmet_status = None

                        if has_helmet_classes:
                            if m2_cls_id in without_helmet_ids:
                                is_rider = True
                                helmet_status = False
                            elif m2_cls_id in with_helmet_ids:
                                is_rider = True
                                helmet_status = True
                            elif m2_cls_id in person_ids:
                                is_rider = True
                                helmet_status = True
                        else:
                            if m2_cls_id in person_ids or m2_cls_id == 0:
                                is_rider = True
                                helmet_status = False

                        logger.info("[DetectionService] Model 2 box: class_id=%d, class_name=%s, conf=%.3f, is_rider=%s, helmet_status=%s",
                                    m2_cls_id, m2_cls_name, float(_val(conf_tensor)), is_rider, helmet_status)

                        if is_rider:
                            riders_count += 1
                            x1_c, y1_c, x2_c, y2_c = box_tensor
                            x1_orig = m_box.x1 + int(_val(x1_c))
                            y1_orig = m_box.y1 + int(_val(y1_c))
                            x2_orig = m_box.x1 + int(_val(x2_c))
                            y2_orig = m_box.y1 + int(_val(y2_c))

                            rider_obj = DetectedObject(
                                id=str(uuid.uuid4()),
                                cls="person",
                                confidence=float(_val(conf_tensor)),
                                bounding_box=BoundingBox(
                                    x1=x1_orig,
                                    y1=y1_orig,
                                    x2=x2_orig,
                                    y2=y2_orig,
                                ),
                                attributes={"helmet": helmet_status},
                                associated_vehicle_id=moto.id,
                            )
                            objects.append(rider_obj)
                else:
                    logger.info("[DetectionService] Model 2 found no boxes inside crop")

                moto.attributes["rider_count"] = riders_count

            return DetectionResult(
                image_id=image_id,
                objects=objects,
                motorcycles=motorcycles,
            )

"""
PaddleOCR wrapper for number plate text extraction.

Requirements: 2.5
"""
from __future__ import annotations

# Patch torchvision.transforms.functional_tensor for basicsr compatibility
import sys
import types
try:
    import torchvision.transforms.functional as F
    if "torchvision.transforms.functional_tensor" not in sys.modules:
        m = types.ModuleType("torchvision.transforms.functional_tensor")
        m.rgb_to_grayscale = F.rgb_to_grayscale
        sys.modules["torchvision.transforms.functional_tensor"] = m
    has_torchvision = True
except ImportError:
    has_torchvision = False

import io
import logging
from PIL import Image

from paddleocr import PaddleOCR

from app.ocr.postprocessor import clean_plate_text

logger = logging.getLogger(__name__)


class OCRPipeline:
    """
    Extract and normalise Indian number plate text from cropped plate images.

    The PaddleOCR engine is initialised once per process instance.
    """

    def __init__(self, model_dir: str = "trained_models") -> None:
        self._ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        logger.info("OCRPipeline initialised")

        # Set up Real-ESRGAN upsampler if torchvision/torch are available
        self._upsampler = None
        if has_torchvision:
            try:
                from pathlib import Path
                model_path = Path(model_dir) / "RealESRGAN_x2plus.pth"
                if model_dir != "dummy" and not model_path.is_file():
                    logger.info("Downloading RealESRGAN_x2plus.pth...")
                    import urllib.request
                    url = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth"
                    try:
                        model_path.parent.mkdir(parents=True, exist_ok=True)
                        urllib.request.urlretrieve(url, str(model_path))
                        logger.info("Downloaded RealESRGAN_x2plus.pth successfully")
                    except OSError as exc:
                        logger.warning("Could not write to %s (%s), falling back to /tmp", model_path, exc)
                        model_path = Path("/tmp/RealESRGAN_x2plus.pth")
                        if not model_path.is_file():
                            logger.info("Downloading RealESRGAN_x2plus.pth to /tmp...")
                            urllib.request.urlretrieve(url, str(model_path))
                            logger.info("Downloaded RealESRGAN_x2plus.pth to /tmp successfully")

                from basicsr.archs.rrdbnet_arch import RRDBNet
                from realesrgan import RealESRGANer

                model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2)
                self._upsampler = RealESRGANer(
                    scale=2,
                    model_path=str(model_path),
                    model=model,
                    tile=0,
                    tile_pad=10,
                    pre_pad=0,
                    half=False
                )
                logger.info("RealESRGANer upsampler initialised")
            except Exception as exc:
                logger.warning("RealESRGANer initialization failed. Enhancement will be bypassed: %s", exc)
        else:
            logger.info("Torchvision/Torch is not available. RealESRGANer enhancement is disabled.")

    def enhance_crop(self, crop_bytes: bytes) -> bytes:
        """
        Upscale the cropped number plate image using Real-ESRGAN.
        """
        if self._upsampler is None:
            return crop_bytes
        try:
            import numpy as np
            import cv2

            # Load Pillow image
            image = Image.open(io.BytesIO(crop_bytes)).convert("RGB")
            img_np = np.array(image)

            # Convert to BGR for RealESRGANer
            img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

            # Enhance
            enhanced_bgr, _ = self._upsampler.enhance(img_bgr, outscale=2)

            # Convert back to RGB and save to JPEG bytes
            enhanced_rgb = cv2.cvtColor(enhanced_bgr, cv2.COLOR_BGR2RGB)
            enhanced_image = Image.fromarray(enhanced_rgb)

            buf = io.BytesIO()
            enhanced_image.save(buf, format="JPEG")
            return buf.getvalue()
        except Exception as exc:
            logger.warning("Real-ESRGAN enhancement failed: %s", exc)
            return crop_bytes

    def read_plate(self, crop_bytes: bytes, enhance: bool = False) -> str | None:
        """
        Run OCR on a plate crop and return normalised plate text.

        Parameters
        ----------
        crop_bytes:
            JPEG/PNG bytes of the cropped number plate region.
        enhance:
            Whether to upscale and sharpen the image with Real-ESRGAN first.

        Returns
        -------
        str | None
            Validated Indian plate string, or ``None`` when OCR fails or the
            text does not match the expected format.
        """
        if enhance:
            crop_bytes = self.enhance_crop(crop_bytes)

        try:
            result = self._ocr.ocr(crop_bytes, cls=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OCR inference failed: %s", exc)
            return None

        if not result or not result[0]:
            return None

        fragments: list[str] = []
        for line in result[0]:
            if line and len(line) >= 2 and line[1]:
                text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                if text:
                    fragments.append(str(text))

        raw = "".join(fragments)
        return clean_plate_text(raw)

    def read_plate_with_crop(self, crop_bytes: bytes) -> tuple[str | None, bytes | None]:
        """
        Run OCR on a vehicle crop.
        Returns:
            plate_text: cleaned plate text
            plate_crop_bytes: bytes of the sub-crop containing the plate, or None
        """
        try:
            result = self._ocr.ocr(crop_bytes, cls=True)
        except Exception as exc:
            logger.warning("OCR inference failed: %s", exc)
            return None, None

        if not result or not result[0]:
            return None, None

        # Load image for sub-cropping
        try:
            image = Image.open(io.BytesIO(crop_bytes)).convert("RGB")
        except Exception:
            image = None

        best_text = None
        best_box = None

        # Try to find a plate by concatenating all text fragments
        fragments: list[str] = []
        boxes: list[list[float]] = []
        for line in result[0]:
            if line and len(line) >= 2 and line[1]:
                text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                if text:
                    fragments.append(str(text))
                    boxes.append(line[0])

        raw_concat = "".join(fragments)
        cleaned_concat = clean_plate_text(raw_concat)

        if cleaned_concat:
            best_text = cleaned_concat
            if boxes:
                all_xs = []
                all_ys = []
                for b in boxes:
                    for pt in b:
                        all_xs.append(pt[0])
                        all_ys.append(pt[1])
                best_box = (min(all_xs), min(all_ys), max(all_xs), max(all_ys))
        else:
            # Fallback: check individual lines
            for line in result[0]:
                if line and len(line) >= 2 and line[1]:
                    text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                    cleaned = clean_plate_text(str(text))
                    if cleaned:
                        best_text = cleaned
                        pts = line[0]
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        best_box = (min(xs), min(ys), max(xs), max(ys))
                        break

        if best_text and image and best_box:
            try:
                x1, y1, x2, y2 = best_box
                w, h = image.size
                pad_x = int((x2 - x1) * 0.05)
                pad_y = int((y2 - y1) * 0.05)
                crop_box = (
                    max(0, int(x1) - pad_x),
                    max(0, int(y1) - pad_y),
                    min(w, int(x2) + pad_x),
                    min(h, int(y2) + pad_y)
                )
                plate_crop = image.crop(crop_box)
                buf = io.BytesIO()
                plate_crop.save(buf, format="JPEG")
                return best_text, buf.getvalue()
            except Exception as exc:
                logger.warning("Failed to crop plate region: %s", exc)
                return best_text, None

        return best_text, None

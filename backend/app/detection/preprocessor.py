"""
Image preprocessor for the TrafficVision AI detection pipeline.

Prepares raw image bytes for YOLOv8m inference by decoding, resizing to the
model's expected input size (640×640), and converting to an RGB numpy array.

Functions
---------
* ``preprocess`` — decode image bytes → resize → convert to RGB ndarray.

Requirements: 2.1
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image


# YOLOv8m inference input size
_INPUT_SIZE: tuple[int, int] = (640, 640)


def preprocess(image_bytes: bytes) -> np.ndarray:
    """Decode, resize, and convert raw image bytes for YOLOv8m inference.

    Accepts any image format that Pillow can decode (JPEG, PNG, etc.).  The
    output is a ``uint8`` NumPy array in **RGB** channel order with shape
    ``(640, 640, 3)``, ready to be passed directly to the Ultralytics
    ``YOLO.predict()`` call.

    Parameters
    ----------
    image_bytes : bytes
        Raw bytes of the original uploaded image.

    Returns
    -------
    np.ndarray
        Preprocessed image array of shape (640, 640, 3) and dtype uint8,
        in RGB channel order.

    Raises
    ------
    ValueError
        If ``image_bytes`` cannot be decoded as a valid image.
    """
    if not image_bytes:
        raise ValueError("image_bytes must not be empty")

    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as exc:
        raise ValueError(f"Cannot decode image bytes: {exc}") from exc

    # Convert to RGB — handles RGBA, palette, grayscale, and other modes
    image = image.convert("RGB")

    # Resize to the model's expected input dimensions using high-quality
    # Lanczos resampling
    image = image.resize(_INPUT_SIZE, resample=Image.Resampling.LANCZOS)

    # Convert to numpy uint8 array with shape (640, 640, 3)
    array: np.ndarray = np.array(image, dtype=np.uint8)

    return array

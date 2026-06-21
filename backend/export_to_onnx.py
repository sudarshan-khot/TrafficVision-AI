"""
ONNX model export utility for TrafficVision AI.

Loads PyTorch weights (.pt) from the trained_models folder,
saves their class mappings to a JSON file, and exports them
to optimized ONNX format.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Configure simple logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def export_pt_to_onnx(model_path: Path, output_dir: Path) -> bool:
    """Load a YOLO .pt model, save its class names to json, and export to ONNX."""
    try:
        from ultralytics import YOLO
    except ImportError:
        logger.error("The 'ultralytics' library is required to export models. Please run: pip install ultralytics")
        return False

    if not model_path.is_file():
        logger.warning("Model file not found: %s", model_path.resolve())
        return False

    logger.info("Loading PyTorch model weights from %s...", model_path.name)
    try:
        model = YOLO(str(model_path))
    except Exception as exc:
        logger.error("Failed to load model %s: %s", model_path.name, exc)
        return False

    # 1. Export class names mapping to json file next to the model
    names_dict = model.names
    names_json_path = output_dir / f"{model_path.stem}.names.json"
    logger.info("Saving class names mapping to %s...", names_json_path.name)
    try:
        # Convert numeric keys to strings for JSON compliance, but ensure type-safety on load
        with open(names_json_path, "w", encoding="utf-8") as f:
            json.dump({int(k): v for k, v in names_dict.items()}, f, indent=2)
        logger.info("Successfully saved class mappings.")
    except Exception as exc:
        logger.error("Failed to save class names mapping: %s", exc)
        return False

    # 2. Export model weights to optimized ONNX
    logger.info("Exporting %s to optimized ONNX format...", model_path.name)
    try:
        # optimize=True activates ONNX model optimization
        onnx_file_path = model.export(format="onnx", optimize=True)
        if onnx_file_path:
            logger.info("Successfully exported ONNX model to: %s", onnx_file_path)
            return True
        else:
            logger.error("Export did not return the output path.")
            return False
    except Exception as exc:
        logger.error("Failed to export ONNX model: %s", exc)
        return False


def main() -> None:
    # Determine the trained_models path relative to the backend/ folder
    backend_root = Path(__file__).resolve().parent
    model_dir = backend_root.parent / "trained_models"

    if not model_dir.is_dir():
        # Fallback to local subdirectory if parent doesn't have it
        model_dir = backend_root / "trained_models"

    if not model_dir.is_dir():
        logger.error("Trained models directory not found at: %s", model_dir.resolve())
        sys.exit(1)

    logger.info("Scanning for model weights in: %s", model_dir.resolve())

    # Supported/expected model filenames
    candidate_names = ["yolov8m.pt", "yolov8n.pt", "yolo26n.pt"]
    exported_count = 0

    for name in candidate_names:
        pt_path = model_dir / name
        if pt_path.is_file():
            success = export_pt_to_onnx(pt_path, model_dir)
            if success:
                exported_count += 1
            print("-" * 60)

    if exported_count > 0:
        logger.info("Export process completed. Exported %d models successfully.", exported_count)
    else:
        logger.warning("No PyTorch weight files (*.pt) were found and exported.")


if __name__ == "__main__":
    main()

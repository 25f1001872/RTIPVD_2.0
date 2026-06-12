"""Download fallback YOLO weights when custom weights are missing."""

from pathlib import Path
from ultralytics import YOLO

WEIGHTS_DIR = Path(__file__).resolve().parent.parent / "weights"


def main():
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)

    custom_weights = WEIGHTS_DIR / "best.pt"
    fallback_weights = WEIGHTS_DIR / "yolov8n.pt"

    if custom_weights.exists():
        size_mb = custom_weights.stat().st_size / (1024 * 1024)
        print(f"[OK] Custom weights found: {custom_weights} ({size_mb:.1f} MB)")
        return

    print(f"[WARNING] Custom weights not found at {custom_weights}")
    print("[INFO] Downloading YOLOv8n pre-trained weights (COCO) as fallback...")

    YOLO("yolov8n.pt")

    # Move downloaded weights to our weights directory
    default_path = Path("yolov8n.pt")
    if default_path.exists():
        default_path.rename(fallback_weights)
        print(f"[OK] Fallback weights saved: {fallback_weights}")
        print("[NOTE] Update config.py MODEL_PATH to use 'yolov8n.pt'")
    else:
        print("[ERROR] Download failed. Check your internet connection.")


if __name__ == "__main__":
    main()
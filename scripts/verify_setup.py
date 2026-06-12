"""
RTIPVD — Setup Verification Script
Run this after installation to verify everything works.

Usage: python scripts/verify_setup.py
"""

import sys
from pathlib import Path


def check(name: str, condition: bool, fix: str = "") -> bool:
    """Print pass/fail for a check."""
    status = "✅ PASS" if condition else "❌ FAIL"
    print(f"  {status}  {name}")
    if not condition and fix:
        print(f"          Fix: {fix}")
    return condition


def main():
    print("\n" + "=" * 60)
    print("  RTIPVD — Setup Verification")
    print("=" * 60 + "\n")

    all_ok = True

    # --- Python Version ---
    print("[1/8] Python Version")
    v = sys.version_info
    all_ok &= check(
        f"Python {v.major}.{v.minor}.{v.micro}",
        v.major == 3 and v.minor == 11,
        "Install Python 3.11.x from python.org",
    )

    # Determine whether CUDA is expected for this profile.
    try:
        from config.config import DEVICE
    except Exception:
        DEVICE = "cuda:0"
    expects_cuda = str(DEVICE).lower().startswith("cuda")

    # --- PyTorch + CUDA ---
    print("\n[2/8] PyTorch + CUDA")
    try:
        import torch
        all_ok &= check(f"PyTorch {torch.__version__}", True)
        if expects_cuda:
            all_ok &= check(
                f"CUDA available: {torch.cuda.is_available()}",
                torch.cuda.is_available(),
                "Reinstall PyTorch with CUDA: pip install torch --index-url https://download.pytorch.org/whl/cu121",
            )
        else:
            all_ok &= check(
                f"CPU profile detected (DEVICE={DEVICE})",
                True,
            )
            check(
                f"CUDA available: {torch.cuda.is_available()} (optional in CPU profile)",
                True,
            )

        if torch.cuda.is_available() and expects_cuda:
            check(f"GPU: {torch.cuda.get_device_name(0)}", True)
    except ImportError:
        all_ok &= check("PyTorch installed", False, "pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")

    # --- Ultralytics ---
    print("\n[3/8] Ultralytics (YOLOv8)")
    try:
        import ultralytics
        all_ok &= check(f"Ultralytics {ultralytics.__version__}", True)
    except ImportError:
        all_ok &= check("Ultralytics installed", False, "pip install ultralytics")

    # --- OpenCV ---
    print("\n[4/8] OpenCV")
    try:
        import cv2
        all_ok &= check(f"OpenCV {cv2.__version__}", True)
    except ImportError:
        all_ok &= check("OpenCV installed", False, "pip install opencv-python")

    # --- NumPy ---
    print("\n[5/8] NumPy")
    try:
        import numpy as np
        is_v1 = int(np.__version__.split(".")[0]) < 2
        all_ok &= check(
            f"NumPy {np.__version__}",
            is_v1,
            "NumPy 2.x breaks some libs. Fix: pip install 'numpy>=1.24.0,<2.0.0'",
        )
    except ImportError:
        all_ok &= check("NumPy installed", False, "pip install numpy")

    # --- EasyOCR ---
    print("\n[6/8] EasyOCR")
    try:
        import easyocr
        all_ok &= check(f"EasyOCR {easyocr.__version__}", True)
    except ImportError:
        all_ok &= check("EasyOCR installed", False, "pip install easyocr")

    # --- Project Files ---
    print("\n[7/8] Project Files")
    root = Path(__file__).resolve().parent.parent

    files = {
        "Model weights": root / "weights" / "best.pt",
        "Test video": root / "data" / "videos" / "d1.mp4",
        "ByteTrack config": root / "config" / "bytetrack.yaml",
        "Config file": root / "config" / "config.py",
        "Main entry": root / "main.py",
    }

    for name, path in files.items():
        all_ok &= check(
            f"{name}: {path.name}",
            path.exists(),
            f"File missing: {path}",
        )

    # --- Module Imports ---
    print("\n[8/8] Module Imports")
    modules = [
        ("config.config", "Configuration"),
        ("src.preprocessing.frame_processor", "Frame Processor"),
        ("src.detection.vehicle_detector", "Vehicle Detector"),
        ("src.detection.vehicle_tracker", "Vehicle Tracker"),
        ("src.ego_motion.lane_detector", "Lane Detector"),
        ("src.ego_motion.motion_estimator", "Ego-Motion Estimator"),
        ("src.analyzer.parking_analyzer", "Parking Analyzer"),
        ("src.analyzer.calibrator", "Threshold Calibrator"),
        ("src.ocr.plate_detector", "Plate Detector"),
        ("src.ocr.plate_reader", "Plate Reader"),
        ("src.visualization.frame_renderer", "Frame Renderer"),
        ("src.visualization.stats_overlay", "Stats Overlay"),
        ("src.database.db_manager", "Database Manager"),
        ("src.database.backend_client", "Backend Client"),
        ("src.evidence.gps_tagger", "GPS Tagger"),
        ("src.evidence.violation_service", "Violation Service"),
        ("src.geospatial.vehicle_geo_mapper", "Geo Mapper"),
        ("src.streaming.packet", "Stream Packet"),
        ("src.streaming.sync", "GPS Sync Buffer"),
    ]

    for module_path, name in modules:
        try:
            __import__(module_path)
            all_ok &= check(f"{name} ({module_path})", True)
        except Exception as e:
            all_ok &= check(
                f"{name} ({module_path})",
                False,
                f"Import error: {e}",
            )

    # --- Final Result ---
    print("\n" + "=" * 60)
    if all_ok:
        print("  🎉 ALL CHECKS PASSED — Ready to run!")
        print("  Execute: python main.py")
    else:
        print("  ⚠️  SOME CHECKS FAILED — Fix the issues above.")
    print("=" * 60 + "\n")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
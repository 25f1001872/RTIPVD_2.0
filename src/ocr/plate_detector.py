"""
===========================================================
RTIPVD — License Plate Region Detector
File: src/ocr/plate_detector.py
===========================================================

Extracts and preprocesses the license plate region from a
vehicle's bounding box for downstream OCR reading.

Responsibilities:
    1. Crop the plate region from the vehicle bounding box
       using heuristic spatial ratios
    2. Preprocess the crop for optimal OCR performance:
       - Grayscale conversion
       - Gaussian blur (noise removal)
       - CLAHE (contrast enhancement under varying lighting)

WHY HEURISTIC CROPPING?
    License plates on Indian vehicles are almost always in the
    bottom 40% of the vehicle body (rear plates) or bottom-center
    (front plates). A simple spatial crop eliminates 60% of the
    bounding box area — reducing OCR search space and false reads.

    For production, a secondary lightweight YOLO model trained
    specifically on license plates would be far more accurate.
    This heuristic approach works well enough for the current stage.

Pipeline position:
    PARKED Vehicle Detected → [THIS MODULE] → Plate Reader (OCR)

Usage:
    from src.ocr.plate_detector import PlateDetector

    detector = PlateDetector()
    crop = detector.extract(frame, x1, y1, x2, y2)
    enhanced = detector.preprocess(crop)
"""

import cv2
import numpy as np

from config.config import (
    PLATE_CROP_TOP_RATIO,
    PLATE_CROP_SIDE_MARGIN,
)


class PlateDetector:
    """
    Detects and preprocesses the license plate region within
    a vehicle bounding box.

    Uses spatial heuristics (bottom 40%, trimmed sides) to
    isolate the plate area, then applies image enhancement
    for optimal OCR accuracy.

    Attributes:
        _clahe (cv2.CLAHE): Pre-initialized CLAHE object for
            contrast enhancement. Created once, reused per call.
        _crop_top (float): Fraction from top where plate crop starts.
        _crop_margin (float): Fraction trimmed from each side.
    """

    def __init__(
        self,
        crop_top_ratio: float = PLATE_CROP_TOP_RATIO,
        crop_side_margin: float = PLATE_CROP_SIDE_MARGIN,
        clahe_clip_limit: float = 2.0,
        clahe_grid_size: tuple = (8, 8),
    ):
        """
        Initialize the plate detector.

        Args:
            crop_top_ratio: Fraction of bbox height where the plate
                            crop starts (measured from top).
                            0.6 means "start at 60% from top" →
                            crops the bottom 40% of the vehicle.
            crop_side_margin: Fraction trimmed from each side of the bbox.
                              0.1 means 10% trimmed from left and right.
                              Removes side mirrors, adjacent vehicles.
            clahe_clip_limit: CLAHE contrast limit. Higher = more contrast
                              but more noise amplification.
            clahe_grid_size: CLAHE tile grid. Smaller = more local adaptation.
        """
        self._crop_top = crop_top_ratio
        self._crop_margin = crop_side_margin

        # Pre-initialize CLAHE to avoid per-frame overhead
        self._clahe = cv2.createCLAHE(
            clipLimit=clahe_clip_limit,
            tileGridSize=clahe_grid_size,
        )

    def extract(
        self,
        frame: np.ndarray,
        x1: int, y1: int,
        x2: int, y2: int,
    ) -> np.ndarray | None:
        """
        Extract the license plate region from a vehicle bounding box.

        Crops the bottom portion of the vehicle bbox where the
        license plate is most likely located, with side margins
        to exclude neighboring objects.

        Coordinate Diagram:
            ┌──────────────────────┐ ← y1
            │                      │
            │   (Vehicle body —    │
            │    ignored by crop)  │
            │                      │
            ├────┬────────────┬────┤ ← y1 + h * crop_top_ratio
            │ M  │            │ M  │   M = side margin (trimmed)
            │ A  │  PLATE     │ A  │
            │ R  │  REGION    │ R  │
            │ G  │  (cropped) │ G  │
            │ I  │            │ I  │
            │ N  │            │ N  │
            └────┴────────────┴────┘ ← y2

        Args:
            frame: Full BGR frame from video (np.ndarray, HxWx3).
            x1, y1: Top-left corner of vehicle bounding box.
            x2, y2: Bottom-right corner of vehicle bounding box.

        Returns:
            np.ndarray: Cropped BGR plate region, or None if the
            resulting crop would have zero area (edge case).
        """
        bbox_h = y2 - y1
        bbox_w = x2 - x1

        # Calculate crop coordinates
        plate_y1 = int(y1 + (bbox_h * self._crop_top))
        plate_y2 = y2
        plate_x1 = int(x1 + (bbox_w * self._crop_margin))
        plate_x2 = int(x2 - (bbox_w * self._crop_margin))

        # Clamp to frame boundaries (prevent out-of-bounds indexing)
        frame_h, frame_w = frame.shape[:2]
        plate_y1 = max(0, plate_y1)
        plate_y2 = min(frame_h, plate_y2)
        plate_x1 = max(0, plate_x1)
        plate_x2 = min(frame_w, plate_x2)

        # Validate crop has non-zero area
        if plate_y2 <= plate_y1 or plate_x2 <= plate_x1:
            return None

        return frame[plate_y1:plate_y2, plate_x1:plate_x2]

    def preprocess(self, crop: np.ndarray) -> np.ndarray:
        """
        Enhance a plate crop for optimal OCR accuracy.

        Pipeline:
            1. BGR → Grayscale (OCR works on single-channel)
            2. Gaussian Blur (5×5) — removes sensor noise and
               high-frequency grain that confuses OCR
            3. CLAHE — adaptive contrast enhancement that
               normalizes brightness across the crop. Critical
               for plates in shadow or under direct sunlight glare.

        Args:
            crop: BGR plate region crop (np.ndarray, HxWx3).

        Returns:
            np.ndarray: Enhanced single-channel (grayscale) image
            optimized for OCR text extraction.
        """
        # Step 1: Convert to grayscale
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        # Step 2: Gaussian blur to remove high-frequency noise
        # Kernel size (5,5) is small enough to preserve text edges
        # but large enough to smooth out sensor grain
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Step 3: CLAHE contrast enhancement
        # Normalizes brightness across the crop so that text
        # "pops" even if half the plate is in shadow
        enhanced = self._clahe.apply(blurred)

        return enhanced

    def __repr__(self) -> str:
        """Readable string representation for debugging."""
        return (
            f"PlateDetector("
            f"crop_top={self._crop_top}, "
            f"margin={self._crop_margin})"
        )
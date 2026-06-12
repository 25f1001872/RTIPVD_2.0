"""
===========================================================
RTIPVD — Vehicle Detector
File: src/detection/vehicle_detector.py
===========================================================

Wraps the YOLOv8 model for vehicle detection and provides
utility methods for class label validation.

Responsibilities:
    1. Load and initialize the YOLOv8 model (custom best.pt)
    2. Expose model metadata (class names, count)
    3. Validate whether a detected class is a vehicle
    4. Provide the raw model for downstream tracking

This module does NOT handle tracking — that's in vehicle_tracker.py.
Separation allows swapping detection models (YOLOv8 → YOLOv9, RT-DETR)
without touching the tracking logic.

Pipeline position:
    PREPROCESSED FRAME → [THIS MODULE] → Tracker → Analyzer

Usage:
    from src.detection.vehicle_detector import VehicleDetector

    detector = VehicleDetector(model_path="weights/best.pt", device="cuda:0")
    is_car = detector.is_vehicle(cls_id=2)
    label  = detector.get_label(cls_id=2)
"""

from ultralytics import YOLO

from config.config import (
    VEHICLE_LABELS,
    VEHICLE_KEYWORDS,
    DEVICE,
)


class VehicleDetector:
    """
    YOLOv8-based vehicle detection wrapper.

    Handles model loading, class label resolution, and vehicle
    classification. The actual inference is delegated to the
    tracker (which calls model.track() internally), but this
    class owns the model instance and label logic.

    Attributes:
        model (YOLO): Loaded YOLOv8 model instance.
        device (str): Device the model runs on ("cuda:0", "cpu").
        class_names (dict): Mapping of class_id → class_name from model.
    """

    def __init__(self, model_path: str, device: str = DEVICE):
        """
        Load the YOLOv8 model onto the specified device.

        Args:
            model_path: Path to the .pt weights file.
                        Example: "weights/best.pt"
            device: Inference device.
                    "cuda:0" for GPU (RTX 4050),
                    "cpu" for CPU-only mode.
        """
        self.model = YOLO(model_path)
        self.device = device

        # Cache class names from the model for fast lookup.
        # Example: {0: "car", 1: "truck", 2: "bus", ...}
        self.class_names = self.model.names

        # Pre-compute the normalized label set for O(1) lookup.
        # This avoids re-normalizing strings on every detection.
        self._normalized_cache = {}

    def get_label(self, cls_id: int) -> str:
        """
        Get the human-readable class label for a YOLO class ID.

        Args:
            cls_id: Integer class ID from YOLO detection.

        Returns:
            str: Class name (e.g., "car", "truck", "motorcycle").
                 Returns "unknown" if cls_id is not in the model.
        """
        return self.class_names.get(cls_id, "unknown")

    def _normalize_label(self, cls_id: int) -> str:
        """
        Normalize a class label by stripping hyphens, underscores,
        and spaces, then lowercasing. Results are cached.

        This handles inconsistent labeling across datasets:
            "motor-cycle" → "motorcycle"
            "Mini Bus"    → "minibus"
            "auto_rickshaw" → "autorickshaw"

        Args:
            cls_id: YOLO class ID.

        Returns:
            str: Normalized lowercase label.
        """
        if cls_id not in self._normalized_cache:
            raw_label = self.get_label(cls_id)
            normalized = (
                raw_label.lower()
                .replace("-", "")
                .replace("_", "")
                .replace(" ", "")
            )
            self._normalized_cache[cls_id] = normalized

        return self._normalized_cache[cls_id]

    def is_vehicle(self, cls_id: int) -> bool:
        """
        Check whether a YOLO class ID corresponds to a vehicle.

        Uses a two-tier matching strategy:
            1. Exact match against VEHICLE_LABELS set (O(1) lookup)
            2. Keyword substring match against VEHICLE_KEYWORDS (fallback)

        This dual approach handles:
            - Standard COCO labels ("car", "truck", "bus")
            - Custom dataset labels ("motor-cycle", "mini_bus")
            - Unexpected but valid labels ("transport_vehicle")

        Args:
            cls_id: Integer class ID from YOLO detection.

        Returns:
            bool: True if the detected object is a vehicle.

        Examples:
            >>> detector.is_vehicle(0)   # cls 0 = "car"
            True
            >>> detector.is_vehicle(15)  # cls 15 = "cat"
            False
        """
        normalized = self._normalize_label(cls_id)

        # Tier 1: Exact match (fast, O(1) set lookup)
        if normalized in VEHICLE_LABELS:
            return True

        # Tier 2: Keyword substring match (catches edge cases)
        return any(keyword in normalized for keyword in VEHICLE_KEYWORDS)

    def get_model(self) -> YOLO:
        """
        Returns the underlying YOLO model instance.

        Used by VehicleTracker to call model.track() directly.
        Keeping this accessor allows future model swapping
        without modifying the tracker.

        Returns:
            YOLO: The loaded ultralytics YOLO model.
        """
        return self.model

    def __repr__(self) -> str:
        """Readable string representation for debugging."""
        num_classes = len(self.class_names)
        return (
            f"VehicleDetector("
            f"classes={num_classes}, "
            f"device='{self.device}', "
            f"model='{type(self.model).__name__}')"
        )
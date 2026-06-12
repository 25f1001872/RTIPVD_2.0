"""
RTIPVD — Detection Module
Handles vehicle detection (YOLOv8) and tracking (ByteTrack).
"""

from src.detection.vehicle_detector import VehicleDetector
from src.detection.vehicle_tracker import VehicleTracker

__all__ = ["VehicleDetector", "VehicleTracker"]
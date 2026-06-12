"""
RTIPVD — OCR Module
Handles license plate detection, preprocessing, reading, and validation.
"""

from src.ocr.plate_detector import PlateDetector
from src.ocr.plate_reader import PlateReader

__all__ = ["PlateDetector", "PlateReader"]
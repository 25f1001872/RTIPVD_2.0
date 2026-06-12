"""
===========================================================
RTIPVD — Validators
File: src/utils/validators.py
===========================================================

Shared validation functions used across modules.
Centralized here to avoid regex duplication.

Usage:
    from src.utils.validators import is_valid_plate, is_vehicle_label

    is_valid_plate("MH12AB1234")  # True
    is_valid_plate("HELLO")       # False
    is_vehicle_label("car")       # True
    is_vehicle_label("cat")       # False
"""

import re
from pathlib import Path

from config.config import (
    PLATE_REGEX_PATTERN,
    VEHICLE_LABELS,
    VEHICLE_KEYWORDS,
)

# Pre-compile regex once at module load
_PLATE_PATTERN = re.compile(PLATE_REGEX_PATTERN)


def is_valid_plate(text: str) -> bool:
    """
    Validate a string against the Indian license plate format.

    Format: [State 2 letters][District 1-2 digits][Series 0-3 letters][Number 1-4 digits]
    Examples: MH12AB1234, RJ01K456, DL3CAB1234

    Args:
        text: Cleaned, uppercase alphanumeric string.

    Returns:
        bool: True if the string matches Indian plate format.
    """
    if not text:
        return False
    return bool(_PLATE_PATTERN.match(text))


def is_vehicle_label(label: str) -> bool:
    """
    Check if a YOLO class label is a vehicle.

    Two-tier matching:
        1. Exact match against VEHICLE_LABELS set
        2. Keyword substring match against VEHICLE_KEYWORDS

    Args:
        label: Raw class label from YOLO model.

    Returns:
        bool: True if the label represents a vehicle.
    """
    normalized = (
        label.lower()
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )

    if normalized in VEHICLE_LABELS:
        return True

    return any(kw in normalized for kw in VEHICLE_KEYWORDS)


def validate_file_exists(path: str, name: str = "File") -> bool:
    """
    Check if a file exists and print a clear error if not.

    Args:
        path: File path to check.
        name: Human-readable name for error messages.

    Returns:
        bool: True if file exists.
    """
    if Path(path).exists():
        return True

    print(f"[ERROR] {name} not found: {path}")
    return False
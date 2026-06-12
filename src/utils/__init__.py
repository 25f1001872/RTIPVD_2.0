"""
RTIPVD — Utilities Module
Shared utility functions used across multiple modules.
"""

from src.utils.logger import get_logger
from src.utils.timer import Timer
from src.utils.validators import is_valid_plate

__all__ = ["get_logger", "Timer", "is_valid_plate"]
"""
===========================================================
RTIPVD — Centralized Logger
File: src/utils/logger.py
===========================================================

Provides a consistent logging setup across all modules.
All modules use this instead of raw print() statements.

Usage:
    from src.utils.logger import get_logger

    logger = get_logger("ModuleName")
    logger.info("Processing frame 42")
    logger.warning("Low lane pixel count")
    logger.error("Model file not found")
"""

import logging
import sys


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Create a configured logger instance.

    Format: [LEVEL] [ModuleName] Message
    Example: [INFO] [ParkingAnalyzer] Vehicle ID:7 classified as PARKED

    Args:
        name: Logger name (typically the module/class name).
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(f"RTIPVD.{name}")

    # Prevent duplicate handlers if get_logger is called multiple times
    if not logger.handlers:
        logger.setLevel(level)

        # Console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)

        # Format: [INFO] [ModuleName] message
        formatter = logging.Formatter(
            fmt="[%(levelname)s] [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
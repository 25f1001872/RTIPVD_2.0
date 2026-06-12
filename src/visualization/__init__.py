"""
RTIPVD — Visualization Module
Handles all frame rendering, bounding box drawing, and stats overlay.
"""

from src.visualization.frame_renderer import FrameRenderer
from src.visualization.stats_overlay import StatsOverlay

__all__ = ["FrameRenderer", "StatsOverlay"]
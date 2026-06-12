"""
===========================================================
RTIPVD — Configuration Template
File: config/config.example.py
===========================================================

Copy this file to config/config.py and modify the values
for your specific setup.

    cp config/config.example.py config/config.py

Then edit config.py with your paths, device, and thresholds.
"""

import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# =============================================================
# CHANGE THESE FOR YOUR SETUP
# =============================================================

# Device: "cuda:0" for NVIDIA GPU, "cpu" for CPU-only
DEVICE = "cuda:0"

# Paths — update these to match your file locations
MODEL_PATH = str(PROJECT_ROOT / "weights" / "best.pt")
VIDEO_SOURCE = str(PROJECT_ROOT / "data" / "videos" / "your_video.mp4")
TRACKER_CONFIG = str(PROJECT_ROOT / "config" / "bytetrack.yaml")

# =============================================================
# USUALLY DON'T NEED TO CHANGE BELOW THIS LINE
# =============================================================

# ... (rest of config.py — see the actual config.py for all settings)
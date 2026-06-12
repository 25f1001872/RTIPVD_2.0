"""
===========================================================
RTIPVD — Real-Time Illegal Parking Vehicle Detection
Configuration Settings
===========================================================

Central configuration file for the entire RTIPVD pipeline.
All tunable parameters, file paths, thresholds, and feature
flags are defined here. No magic numbers in other files.

Structure:
    1. System & Device Settings
    2. File Paths
    3. Timing Thresholds
    4. Motion Calibration
    5. Bounding Box Constraints
    6. Centroid Smoothing & Tracking
    7. Ego-Motion (Optical Flow / Lane Detection)
    8. Vehicle Class Definitions
    9. License Plate / OCR Settings
    10. Visualization & Debug Flags
    11. Phase 2 Settings (Future — commented out)
"""

import os
import numpy as np
from pathlib import Path


def _env_str(key: str, default: str) -> str:
    """Read a string environment variable with a fallback default."""
    value = os.getenv(key)
    return value if value is not None else default


def _env_int(key: str, default: int) -> int:
    """Read an integer environment variable with a safe fallback."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    """Read a float environment variable with a safe fallback."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    """Read a boolean environment variable using common true/false strings."""
    value = os.getenv(key)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _resolve_path(path_value: str) -> str:
    """Resolve relative paths from project root while preserving absolute paths."""
    path = Path(path_value)
    if path.is_absolute():
        return str(path)
    return str((PROJECT_ROOT / path).resolve())


# =============================================================
# 1. SYSTEM & DEVICE SETTINGS
# =============================================================

# Automatically resolves to the project root directory
# (config/ is one level inside root, so .parent goes up one)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Device selection for YOLO inference
# Options: "cuda:0" (GPU), "cpu", or "auto" (let ultralytics decide)
DEVICE = _env_str("RTIPVD_DEVICE", "cuda:0")


# =============================================================
# 2. FILE PATHS
#    All paths are relative to PROJECT_ROOT for portability.
#    Use (PROJECT_ROOT / "subpath") for absolute resolution.
# =============================================================

MODEL_PATH = _resolve_path(_env_str("RTIPVD_MODEL_PATH", "weights/best.pt"))
VIDEO_SOURCE = _resolve_path(_env_str("RTIPVD_VIDEO_SOURCE", "data/videos/d1.mp4"))
TRACKER_CONFIG = _resolve_path(_env_str("RTIPVD_TRACKER_CONFIG", "config/bytetrack.yaml"))

# Output directories (auto-created at runtime if missing)
OUTPUT_DIR = _resolve_path(_env_str("RTIPVD_OUTPUT_DIR", "output"))
VIOLATIONS_DIR = _resolve_path(_env_str("RTIPVD_VIOLATIONS_DIR", "output/violations"))
SCREENSHOTS_DIR = _resolve_path(_env_str("RTIPVD_SCREENSHOTS_DIR", "output/violations/screenshots"))
LOGS_DIR = _resolve_path(_env_str("RTIPVD_LOGS_DIR", "output/violations/logs"))
RESULTS_DIR = _resolve_path(_env_str("RTIPVD_RESULTS_DIR", "output/results"))


# =============================================================
# 3. TIMING THRESHOLDS (in seconds)
#    Controls how long a vehicle must remain stationary
#    before it is classified as PARKED.
# =============================================================

# Minimum duration a vehicle must be stationary to be flagged.
# Example: 5.0 seconds → a car stopped at a red light for
# 3 seconds will NOT be flagged. Only truly parked vehicles.
PARKED_SECONDS = 5.0

# If a tracked vehicle disappears (e.g., occluded by a truck)
# for longer than this, its tracking state is deleted from memory.
STALE_TRACK_SECONDS = 2.0

# Vehicle must be continuously visible for at least this duration
# before any parking decision is made. Filters out brief ghost
# detections that appear for 1-2 frames and vanish.
MIN_VISIBLE_SECONDS = 0.6


# =============================================================
# 4. MOTION CALIBRATION
#    Auto-calibration tunes the stationary threshold to the
#    specific video's resolution, camera speed, and scene.
# =============================================================

# Number of initial frames used to collect motion samples
# for auto-calibration. During these frames, no parking
# decisions are made — the system is "learning" the scene.
CALIBRATION_FRAMES = 60

# After calibration, the threshold is set to:
#   threshold = clamp(P80 * 1.5, MIN, MAX)
# where P80 = 80th percentile of observed motion magnitudes.
MIN_STATIONARY_THRESHOLD = 3.0   # Floor: prevents threshold going too low
MAX_STATIONARY_THRESHOLD = 20.0  # Ceiling: prevents threshold going too high

# Percentile used for calibration (80 = P80)
CALIBRATION_PERCENTILE = 80

# Multiplier applied to the percentile value
CALIBRATION_MULTIPLIER = 1.5


# =============================================================
# 5. BOUNDING BOX CONSTRAINTS
#    Filters out vehicles that are too far (tiny bbox) or
#    too close (huge bbox) where motion analysis is unreliable.
# =============================================================

# Vehicles with bbox height below this are TOO FAR from camera.
# Their pixel-level motion is near zero even when driving.
# Parking analysis would produce false positives.
MIN_BBOX_HEIGHT = 120  # pixels

# Vehicles with bbox height above this are TOO CLOSE to camera.
# Perspective distortion makes motion estimation unreliable.
MAX_BBOX_HEIGHT = 800  # pixels


# =============================================================
# 6. CENTROID SMOOTHING & TRACKING TOLERANCES
#    Handles YOLO bounding box jitter to prevent false
#    classification of parked vehicles as "moving".
# =============================================================

# Exponential Moving Average (EMA) smoothing factor for centroids.
# Formula: smoothed = alpha * current + (1 - alpha) * previous
#   - Lower alpha (e.g., 0.2) = smoother, slower to react
#   - Higher alpha (e.g., 0.8) = noisier, faster to react
#   - 0.35 is a balanced sweet spot for YOLO bbox jitter
CENTROID_EMA_ALPHA = 0.35

# Number of consecutive "moving" frames tolerated before resetting
# the stationary counter. Absorbs brief jitter spikes.
# Example: A parked car's bbox jitters for 5 frames →
#   forgiveness absorbs it. If jitter lasts 11+ frames →
#   counter resets (vehicle is actually moving).
FORGIVENESS_FRAMES = 10


# =============================================================
# 7. EGO-MOTION: OPTICAL FLOW & LANE DETECTION
#    Lane markings are used as road-surface anchors.
#    Their optical flow = exact camera ego-motion.
# =============================================================

# Maximum number of feature points to track per frame.
# More points = more robust homography but slower computation.
MAX_LANE_FEATURES = 2500

# Minimum number of lane feature points required for
# reliable homography computation. Below this, the system
# falls back to generic background features.
MIN_LANE_FEATURES = 15

# HSV color range for detecting WHITE lane markings.
# V (Value/Brightness) threshold lowered to 100 to catch
# lanes in deep shadows. S (Saturation) capped at 60 to
# exclude colored objects that happen to be bright.
WHITE_HSV_LO = np.array([0,   0, 100], dtype=np.uint8)
WHITE_HSV_HI = np.array([180, 60, 255], dtype=np.uint8)

# HSV color range for YELLOW lane markings (uncomment if needed).
# YELLOW_HSV_LO = np.array([15,  80, 100], dtype=np.uint8)
# YELLOW_HSV_HI = np.array([35, 255, 255], dtype=np.uint8)

# Fraction of frame height to ignore from the top.
# Everything above this line is treated as sky/buildings/trees
# and excluded from lane detection. 0.5 = top 50% ignored.
HORIZON_RATIO = 0.5

# Padding (in pixels) around vehicle bounding boxes when
# masking them out of the lane detection mask. Prevents
# vehicle body edges from being mistaken as lane features.
VEHICLE_MASK_PADDING = 12


# =============================================================
# 8. VEHICLE CLASS DEFINITIONS
#    Two-tier matching: exact label set + keyword fallback.
#    Supports both COCO-pretrained and custom-trained models.
# =============================================================

# Exact lowercase match (after stripping hyphens/underscores/spaces)
VEHICLE_LABELS = {
    "motorbike", "motorcycle", "scooter",
    "car", "suv", "van", "pickup",
    "truck", "bus", "minibus",
    "tractor", "trailer",
    "rickshaw", "autorickshaw",
    "ambulance", "firetruck",
}

# Fallback keyword matching — if exact match fails, check if
# any of these substrings appear in the class label.
# Catches custom dataset labels like "motor-cycle", "mini_bus", etc.
VEHICLE_KEYWORDS = (
    "moto", "scooter", "car", "suv", "van",
    "truck", "bus", "pickup", "tractor",
    "trailer", "rickshaw", "vehicle",
)


# =============================================================
# 9. LICENSE PLATE / OCR SETTINGS
#    Controls the EasyOCR pipeline for reading plates on
#    vehicles classified as PARKED.
# =============================================================

# Whether to use a mock/fake plate reader (for testing without
# GPU-heavy EasyOCR model loading). Set True during development.
USE_MOCK_OCR = _env_bool("RTIPVD_USE_MOCK_OCR", False)

# OCR language — 'en' for English/alphanumeric plates
OCR_LANGUAGE = ['en']

# Use GPU for EasyOCR inference (recommended with your RTX 4050)
OCR_USE_GPU = _env_bool("RTIPVD_OCR_USE_GPU", True)

# Rolling window size for temporal majority voting.
# Plate text is read across multiple frames; the most
# frequently occurring string in the last N reads wins.
# Higher = more stable but slower to converge.
OCR_HISTORY_WINDOW = 7

# Fraction of vehicle bbox to crop for plate region.
# Plates are typically in the bottom 40% of the vehicle.
PLATE_CROP_TOP_RATIO = 0.6     # Start crop at 60% from top
PLATE_CROP_SIDE_MARGIN = 0.1   # Trim 10% from each side

# Indian license plate regex pattern.
# Matches: MH12AB1234, RJ01K456, DL3CAB1234, etc.
# Format: [State 2 letters][District 1-2 digits][Series 0-3 letters][Number 1-4 digits]
PLATE_REGEX_PATTERN = r"^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{1,4}$"


# =============================================================
# 10. VISUALIZATION & DEBUG FLAGS
# =============================================================

# Show green-tinted lane mask overlay on the output frame.
# Useful for debugging ego-motion. Set False for clean output.
DEBUG_LANE_OVERLAY = _env_bool("RTIPVD_DEBUG_LANE_OVERLAY", True)

# Show the output window (set False for headless/server mode)
SHOW_DISPLAY = _env_bool("RTIPVD_SHOW_DISPLAY", True)

# Window name for OpenCV display
WINDOW_NAME = _env_str("RTIPVD_WINDOW_NAME", "RTIPVD — Parking Detection System")


# =============================================================
# 11. PHASE 2 SETTINGS (Database, GPS, Backend API)
# =============================================================

# --- Database ---
DB_ENABLED = _env_bool("RTIPVD_DB_ENABLED", True)
DB_PATH = _resolve_path(_env_str("RTIPVD_DB_PATH", "output/db/rtipvd.db"))
DB_MERGE_WINDOW_SECONDS = _env_float("RTIPVD_DB_MERGE_WINDOW_SECONDS", 120.0)

# --- GPS ---
GPS_ENABLED = _env_bool("RTIPVD_GPS_ENABLED", False)
GPS_SOURCE = _env_str("RTIPVD_GPS_SOURCE", "serial")  # Options: serial, mock
GPS_SERIAL_PORT = _env_str("RTIPVD_GPS_SERIAL_PORT", "/dev/ttyUSB0")
GPS_BAUD_RATE = _env_int("RTIPVD_GPS_BAUD_RATE", 9600)
GPS_READ_TIMEOUT_MS = _env_int("RTIPVD_GPS_READ_TIMEOUT_MS", 300)
# GPS_MOCK_LAT and GPS_MOCK_LON should be in DECIMAL DEGREES (already converted from ddmm.mmmm format)
# Example: 2951.6747 → 29.861245, 7753.8555 → 77.897592
GPS_MOCK_LAT = _env_float("RTIPVD_GPS_MOCK_LAT", 29.861245)
GPS_MOCK_LON = _env_float("RTIPVD_GPS_MOCK_LON", 77.897592)

# --- Backend Upload ---
BACKEND_ENABLED = _env_bool("RTIPVD_BACKEND_ENABLED", False)
BACKEND_URL = _env_str("RTIPVD_BACKEND_URL", "http://127.0.0.1:5000/api/violations")
BACKEND_API_KEY = _env_str("RTIPVD_BACKEND_API_KEY", "")
BACKEND_TIMEOUT_SEC = _env_float("RTIPVD_BACKEND_TIMEOUT_SEC", 5.0)
BACKEND_VERIFY_SSL = _env_bool("RTIPVD_BACKEND_VERIFY_SSL", True)

# --- Dashboard Backend Host ---
DASHBOARD_HOST = _env_str("RTIPVD_DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = _env_int("RTIPVD_DASHBOARD_PORT", 5000)
DASHBOARD_DEBUG = _env_bool("RTIPVD_DASHBOARD_DEBUG", False)

# --- Stream Transport (Pi -> Laptop) ---
STREAM_SERVER_HOST = _env_str("RTIPVD_STREAM_SERVER_HOST", "0.0.0.0")
STREAM_SERVER_PORT = _env_int("RTIPVD_STREAM_SERVER_PORT", 8088)
STREAM_SERVER_URL = _env_str("RTIPVD_STREAM_SERVER_URL", "http://127.0.0.1:8088/ingest/frame")
STREAM_SEND_FPS = _env_float("RTIPVD_STREAM_SEND_FPS", 8.0)
STREAM_JPEG_QUALITY = _env_int("RTIPVD_STREAM_JPEG_QUALITY", 70)
STREAM_DEFAULT_HEADING_DEG = _env_float("RTIPVD_STREAM_DEFAULT_HEADING_DEG", 0.0)
STREAM_COORD_INPUT_FORMAT = _env_str("RTIPVD_STREAM_COORD_INPUT_FORMAT", "auto").strip().lower()
STREAM_COORD_UTM_ZONE = _env_int("RTIPVD_STREAM_COORD_UTM_ZONE", 43)
STREAM_COORD_UTM_HEMISPHERE = _env_str("RTIPVD_STREAM_COORD_UTM_HEMISPHERE", "N").strip().upper()
# --- Illegal Parking Geofence ---
ILLEGAL_PARKING_GEOJSON_ENABLED = _env_bool("RTIPVD_ILLEGAL_PARKING_GEOJSON_ENABLED", True)
ILLEGAL_PARKING_GEOJSON_PATH = _resolve_path(
    _env_str("RTIPVD_ILLEGAL_PARKING_GEOJSON_PATH", "data/geofencing/No_Parking_Zones.geojson")
)
GEO_MAPPER_HFOV_DEG = _env_float("RTIPVD_GEO_MAPPER_HFOV_DEG", 78.0)
ILLEGAL_PARKING_DEFAULT_HEADING_DEG = _env_float(
    "RTIPVD_ILLEGAL_PARKING_DEFAULT_HEADING_DEG",
    STREAM_DEFAULT_HEADING_DEG,
)

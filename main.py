"""
===========================================================
RTIPVD — Real-Time Illegal Parking Vehicle Detection
File: main.py (Entry Point)
===========================================================

Main orchestrator that ties all modules together into a
single real-time detection pipeline.

Pipeline Flow:
    Video Input
        → Frame Preprocessing (brightness, CLAHE night-mode)
        → Dual Parallel Pipeline:
            → Vehicle Detection (YOLOv8) + Tracking (ByteTrack)
            → Lane Detection (HSV) + Ego-Motion (LK + Homography)
        → Motion Analysis (ego-compensated true motion)
        → Parking Decision (adaptive threshold + forgiveness)
        → License Plate OCR (PARKED vehicles only)
        → Visualization (color-coded bboxes + stats overlay)
        → Display / Output

Modules Used:
    config.config           → All configuration parameters
    src.preprocessing       → Frame cleaning and enhancement
    src.detection           → YOLOv8 detection + ByteTrack tracking
    src.ego_motion          → Lane detection + camera motion estimation
    src.analyzer            → Parking classification + calibration
    src.ocr                 → License plate reading + validation
    src.visualization       → Bounding box rendering + stats overlay

Usage:
    python main.py

Controls:
    Press 'q' to quit the application.

Hardware:
    Optimized for NVIDIA RTX 4050 GPU with CUDA 12.1
    Python 3.11.9
"""

import sys
import cv2

from config.config import (
    VIDEO_SOURCE,
    MODEL_PATH,
    TRACKER_CONFIG,
    DEVICE,
    DEBUG_LANE_OVERLAY,
    SHOW_DISPLAY,
    WINDOW_NAME,
    ILLEGAL_PARKING_GEOJSON_ENABLED,
    ILLEGAL_PARKING_GEOJSON_PATH,
    GEO_MAPPER_HFOV_DEG,
    ILLEGAL_PARKING_DEFAULT_HEADING_DEG,
)

from src.preprocessing.frame_processor import FrameProcessor
from src.detection.vehicle_detector import VehicleDetector
from src.detection.vehicle_tracker import VehicleTracker
from src.ego_motion.lane_detector import LaneDetector
from src.ego_motion.motion_estimator import EgoMotionEstimator
from src.analyzer.parking_analyzer import ParkingAnalyzer
from src.database.backend_client import BackendClient
from src.database.db_manager import DatabaseManager
from src.evidence.gps_tagger import GPSTagger
from src.evidence.violation_service import ViolationService
from src.geospatial.vehicle_geo_mapper import VehicleGeoMapper
from src.geospatial.zone_checker import NoParkingZoneChecker
from src.ocr.plate_reader import PlateReader
from src.visualization.frame_renderer import FrameRenderer
from src.visualization.stats_overlay import StatsOverlay


def initialize_video(source: str) -> tuple:
    """
    Open the video source and extract FPS.

    Args:
        source: Path to video file or camera index.

    Returns:
        tuple: (cv2.VideoCapture, fps) or (None, 0) on failure.
    """
    cap = cv2.VideoCapture(source)

    if not cap.isOpened():
        print(f"[ERROR] Cannot open video source: {source}")
        return None, 0.0

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30.0
        print(f"[WARNING] Could not read FPS from video. Defaulting to {fps}")

    # Read video metadata for logging
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"[VIDEO] Source: {source}")
    print(f"[VIDEO] Resolution: {width}x{height} | FPS: {fps:.1f} | Frames: {total_frames}")

    return cap, fps


def initialize_modules(fps: float, video_source: str) -> dict:
    """
    Initialize all pipeline modules.

    Creates and configures every component of the detection pipeline.
    Modules are returned as a dictionary for clean access in the
    main loop without cluttering the namespace.

    Args:
        fps: Video frames per second (used for time-based thresholds).

    Returns:
        dict: Dictionary of initialized module instances.
    """
    print("\n[INIT] Initializing RTIPVD pipeline modules...")
    print(f"[INIT] Device: {DEVICE}")

    # --- Detection & Tracking ---
    print("[INIT] Loading YOLOv8 model...")
    detector = VehicleDetector(model_path=MODEL_PATH, device=DEVICE)
    tracker = VehicleTracker(detector=detector, tracker_config=TRACKER_CONFIG)
    print(f"[INIT] {detector}")

    # --- Preprocessing ---
    preprocessor = FrameProcessor()

    # --- Ego-Motion ---
    lane_detector = LaneDetector()
    ego_estimator = EgoMotionEstimator()

    # --- Parking Analysis ---
    analyzer = ParkingAnalyzer(fps=fps)

    # --- License Plate OCR ---
    plate_reader = PlateReader()
    print(f"[INIT] {plate_reader}")

    # --- Visualization ---
    renderer = FrameRenderer()
    overlay = StatsOverlay()

    # --- Evidence + Persistence + Backend Sync ---
    db_manager = DatabaseManager()
    gps_tagger = GPSTagger()
    backend_client = BackendClient()
    geo_mapper = VehicleGeoMapper(horizontal_fov_deg=GEO_MAPPER_HFOV_DEG)
    zone_checker = NoParkingZoneChecker(
        enabled=ILLEGAL_PARKING_GEOJSON_ENABLED,
        geojson_path=ILLEGAL_PARKING_GEOJSON_PATH,
    )
    violation_service = ViolationService(
        db_manager=db_manager,
        gps_tagger=gps_tagger,
        backend_client=backend_client,
        video_source=video_source,
        geo_mapper=geo_mapper,
        zone_checker=zone_checker,
        default_heading_deg=ILLEGAL_PARKING_DEFAULT_HEADING_DEG,
    )

    print(f"[INIT] {db_manager}")
    print(f"[INIT] {gps_tagger}")
    print(f"[INIT] {backend_client}")
    print(f"[INIT] {geo_mapper}")
    print(f"[INIT] {zone_checker}")

    print("[INIT] All modules initialized successfully.\n")

    return {
        "detector": detector,
        "tracker": tracker,
        "preprocessor": preprocessor,
        "lane_detector": lane_detector,
        "ego_estimator": ego_estimator,
        "analyzer": analyzer,
        "plate_reader": plate_reader,
        "renderer": renderer,
        "overlay": overlay,
        "violation_service": violation_service,
    }


def process_frame(
    result,
    frame_idx: int,
    modules: dict,
) -> None:
    """
    Process a single frame through the entire pipeline.

    This is the core per-frame logic, extracted from the main loop
    for clarity. Each step is clearly separated and commented.

    Args:
        result: YOLO tracking result for this frame.
        frame_idx: Current frame number (1-indexed).
        modules: Dictionary of initialized pipeline modules.
    """
    # Unpack modules for readability
    preprocessor = modules["preprocessor"]
    tracker = modules["tracker"]
    lane_detector = modules["lane_detector"]
    ego_estimator = modules["ego_estimator"]
    analyzer = modules["analyzer"]
    plate_reader = modules["plate_reader"]
    renderer = modules["renderer"]
    overlay = modules["overlay"]
    violation_service = modules["violation_service"]

    # Get original frame and detection boxes
    orig_frame = result.orig_img.copy()
    boxes = result.boxes

    # Per-frame plate read cache (avoid duplicate OCR calls
    # for the same vehicle within one frame)
    read_plates = {}

    # ==========================================================
    # STAGE 1: PREPROCESSING
    # YOLO already processed the raw frame internally, but we
    # need a cleaned version for:
    #   - Optical flow (grayscale, enhanced if dark)
    #   - Final display (brightness-corrected)
    # ==========================================================
    cleaned_frame, gray, avg_brightness = preprocessor.process(orig_frame)
    display_frame = cleaned_frame.copy()

    # ==========================================================
    # STAGE 2: LANE DETECTION + EGO-MOTION ESTIMATION
    # Detect lane markings → track them with optical flow →
    # compute homography → extract camera translation.
    # ==========================================================
    lane_mask, lane_px_count = lane_detector.detect(cleaned_frame, boxes)
    H_ego, lane_dx, lane_dy, _ = ego_estimator.compute(gray, lane_mask, lane_px_count)

    # ==========================================================
    # STAGE 3: LANE DEBUG OVERLAY (optional)
    # Green tint over detected lane pixels — shows evaluators
    # exactly which pixels the system is using as ego-motion anchors.
    # ==========================================================
    if DEBUG_LANE_OVERLAY:
        display_frame = renderer.draw_lane_overlay(display_frame, lane_mask)

    # ==========================================================
    # STAGE 4: PER-VEHICLE ANALYSIS
    # For each tracked vehicle: compute ego-compensated motion,
    # classify as PARKED/MOVING/OUT_OF_RANGE, read plate if parked.
    # ==========================================================
    if boxes is not None:
        for box in boxes:
            # --- Extract detection data ---
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            track_id = int(box.id[0]) if box.id is not None else -1
            cls_id = int(box.cls[0])
            confidence = float(box.conf[0]) if box.conf is not None else None

            # --- Filter: skip non-vehicles and untracked detections ---
            if track_id < 0 or not tracker.is_vehicle(cls_id):
                continue

            # --- Compute bounding box center and height ---
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            bbox_h = y2 - y1

            # --- Parking status analysis ---
            status, motion_mag = analyzer.analyze_vehicle(
                track_id, cx, cy, bbox_h,
                frame_idx, H_ego, lane_dx, lane_dy,
            )

            # --- License plate OCR (PARKED vehicles only) ---
            plate_text = ""
            if status == "PARKED":
                if track_id not in read_plates:
                    plate_text = plate_reader.read(
                        orig_frame, x1, y1, x2, y2, track_id,
                    )
                    read_plates[track_id] = plate_text
                else:
                    plate_text = read_plates[track_id]

                violation_service.report_parked(
                    track_id=track_id,
                    plate_text=plate_text,
                    frame_idx=frame_idx,
                    confidence=confidence,
                    bbox_xyxy=(x1, y1, x2, y2),
                    frame_shape=orig_frame.shape[:2],
                )

            # --- Draw vehicle annotation ---
            renderer.draw_vehicle(
                display_frame,
                x1, y1, x2, y2,
                track_id, status, motion_mag, plate_text,
            )

            # --- Extra highlight for parked vehicles ---
            if status == "PARKED":
                renderer.draw_parked_highlight(
                    display_frame, x1, y1, x2, y2,
                    pulse=(frame_idx % 20 < 10),  # Blink effect
                )

    # ==========================================================
    # STAGE 5: MEMORY CLEANUP
    # Remove tracking state for vehicles that haven't been
    # detected for STALE_TRACK_SECONDS. Also clean up their
    # plate reading history.
    # ==========================================================
    track_ids_before = set(analyzer.track_states.keys())
    purged_count = analyzer.purge_stale_tracks(frame_idx)
    track_ids_after = set(analyzer.track_states.keys())
    purged_track_ids = track_ids_before - track_ids_after

    # Clean plate history for purged tracks
    if purged_count > 0:
        for tid in purged_track_ids:
            plate_reader.clear_track(tid)

    violation_service.close_inactive_tracks(track_ids_after)

    # ==========================================================
    # STAGE 6: STATS OVERLAY
    # Draw the real-time statistics bar at the top of the frame.
    # ==========================================================
    overlay.draw(
        display_frame,
        brightness=avg_brightness,
        threshold=analyzer.stationary_threshold,
        lane_dx=lane_dx,
        lane_dy=lane_dy,
        lane_px_count=lane_px_count,
        track_count=analyzer.get_active_track_count(),
        is_calibrated=analyzer.calibrator.is_calibrated,
    )

    # ==========================================================
    # STAGE 7: DISPLAY
    # ==========================================================
    if SHOW_DISPLAY:
        cv2.imshow(WINDOW_NAME, display_frame)


def main():
    """
    RTIPVD main entry point.

    Initializes all modules, opens the video source, and runs
    the frame-by-frame processing loop until the video ends
    or the user presses 'q'.
    """
    print("=" * 60)
    print("  RTIPVD — Real-Time Illegal Parking Vehicle Detection")
    print("  IIT Roorkee | 2025")
    print("=" * 60)

    # ----------------------------------------------------------
    # Step 1: Open video source
    # ----------------------------------------------------------
    cap, fps = initialize_video(VIDEO_SOURCE)
    if cap is None:
        sys.exit(1)

    # ----------------------------------------------------------
    # Step 2: Initialize all pipeline modules
    # ----------------------------------------------------------
    modules = initialize_modules(fps, VIDEO_SOURCE)

    # ----------------------------------------------------------
    # Step 3: Start tracking stream
    # YOLO's model.track() returns a generator that yields
    # one result per frame — detection + tracking combined.
    # ----------------------------------------------------------
    print("[RUNNING] Starting detection pipeline...")
    print("[RUNNING] Press 'q' to stop.\n")

    results_generator = modules["tracker"].stream(source=VIDEO_SOURCE)
    frame_idx = 0

    # ----------------------------------------------------------
    # Step 4: Main processing loop
    # ----------------------------------------------------------
    try:
        for result in results_generator:
            frame_idx += 1

            # Process this frame through the entire pipeline
            process_frame(result, frame_idx, modules)

            # Check for quit key
            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("\n[STOPPED] User pressed 'q'. Shutting down...")
                break

    except KeyboardInterrupt:
        print("\n[STOPPED] KeyboardInterrupt received. Shutting down...")

    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        raise

    finally:
        # ----------------------------------------------------------
        # Step 5: Cleanup
        # Release video capture and close all OpenCV windows.
        # The finally block ensures cleanup happens even on errors.
        # ----------------------------------------------------------
        cap.release()
        cv2.destroyAllWindows()

        modules["violation_service"].close()

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"  Session Summary")
        print(f"  Frames processed: {frame_idx}")
        print(f"  Active tracks at exit: {modules['analyzer'].get_active_track_count()}")
        print(f"  Final threshold: {modules['analyzer'].stationary_threshold:.2f}px")
        print(f"  Calibration: {'Complete' if modules['analyzer'].calibrator.is_calibrated else 'Incomplete'}")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
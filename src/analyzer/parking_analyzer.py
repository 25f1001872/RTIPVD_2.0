"""
===========================================================
RTIPVD — Parking Analyzer
File: src/analyzer/parking_analyzer.py
===========================================================

Core decision engine that determines whether each tracked
vehicle is PARKED, MOVING, or OUT_OF_RANGE.

Responsibilities:
    1. Maintain per-vehicle tracking state (smoothed centroid,
       stationary counter, visibility counter, jitter counter)
    2. Compute ego-compensated motion for each vehicle
    3. Apply EMA centroid smoothing to dampen YOLO bbox jitter
    4. Classify vehicles using time-based thresholds
    5. Purge stale tracks from memory
    6. Delegate threshold calibration to ThresholdCalibrator

Decision Logic:
    - OUT_OF_RANGE: bbox height outside [MIN, MAX] → skip entirely
    - MOVING: ego-compensated motion > threshold (consistently)
    - PARKED: stationary for >= PARKED_SECONDS AND visible >= MIN_VISIBLE_SECONDS

Jitter Handling:
    YOLO bounding boxes wobble slightly every frame. Without handling,
    a parked car's centroid appears to "move" 1-3 pixels per frame.
    Two mechanisms prevent false classification:
        1. EMA smoothing (α=0.35) — dampens centroid noise
        2. Forgiveness frames (10) — tolerates brief motion spikes

Pipeline position:
    Ego-Motion → [THIS MODULE] → OCR (for PARKED only) → Display

Usage:
    from src.analyzer.parking_analyzer import ParkingAnalyzer

    analyzer = ParkingAnalyzer(fps=30.0)
    status, motion = analyzer.analyze_vehicle(
        track_id, cx, cy, bbox_h, frame_idx, H_ego, lane_dx, lane_dy
    )
"""

import cv2
import numpy as np

from config.config import (
    PARKED_SECONDS,
    STALE_TRACK_SECONDS,
    MIN_VISIBLE_SECONDS,
    MIN_BBOX_HEIGHT,
    MAX_BBOX_HEIGHT,
    CENTROID_EMA_ALPHA,
    FORGIVENESS_FRAMES,
)

from src.analyzer.calibrator import ThresholdCalibrator


class ParkingAnalyzer:
    """
    Analyzes tracked vehicles to determine parking status.

    Maintains a dictionary of per-vehicle states keyed by track_id.
    Each state tracks:
        - Smoothed centroid (scx, scy) — EMA-filtered position
        - Stationary frame counter — consecutive frames with low motion
        - Jitter frame counter — consecutive frames with high motion
        - Visibility counter — total frames this vehicle has been seen
        - Last seen frame — for stale track purging

    Attributes:
        parked_frames (int): Frames a vehicle must be stationary to be PARKED.
        min_visible_frames (int): Minimum frames visible before any decision.
        stale_track_frames (int): Frames after which unseen tracks are purged.
        calibrator (ThresholdCalibrator): Auto-calibrates the stationary threshold.
        track_states (dict): Per-vehicle state dictionary.
    """

    def __init__(self, fps: float):
        """
        Initialize the parking analyzer.

        Converts time-based thresholds (seconds) to frame counts
        using the video's FPS. This makes the system FPS-independent —
        PARKED_SECONDS=5.0 means 5 real seconds whether the video
        is 24fps, 30fps, or 60fps.

        Args:
            fps: Frames per second of the input video.
                 Used to convert seconds → frame counts.
        """
        # Convert seconds → frames for this specific video's FPS
        self.parked_frames = int(PARKED_SECONDS * fps)
        self.min_visible_frames = int(MIN_VISIBLE_SECONDS * fps)
        self.stale_track_frames = int(STALE_TRACK_SECONDS * fps)

        # Per-vehicle tracking states: {track_id: state_dict}
        self.track_states = {}

        # Adaptive threshold calibrator (auto-tunes in first 60 frames)
        self.calibrator = ThresholdCalibrator()

    @property
    def stationary_threshold(self) -> float:
        """
        Current stationary threshold in pixels.

        Exposed as a property so the display module can show it
        in the stats overlay bar without accessing the calibrator directly.
        """
        return self.calibrator.get_threshold()

    def analyze_vehicle(
        self,
        track_id: int,
        cx: float,
        cy: float,
        bbox_h: int,
        frame_idx: int,
        H_ego: np.ndarray,
        lane_dx: float,
        lane_dy: float,
    ) -> tuple:
        """
        Analyze a single tracked vehicle and classify its status.

        Algorithm:
            1. Distance filter — reject too far / too close vehicles
            2. Retrieve or initialize per-vehicle state
            3. Apply EMA smoothing on centroid coordinates
            4. Compute ego-compensated motion:
               a. If homography available: project previous centroid
                  through H_ego → compare with actual current position
               b. Fallback: subtract lane-average translation (dx, dy)
            5. Update stationary / jitter counters based on threshold
            6. Feed motion sample to calibrator (first 60 frames)
            7. Classify as PARKED or MOVING based on duration thresholds

        Args:
            track_id: Unique vehicle ID assigned by ByteTrack.
            cx: Current x-coordinate of bounding box center.
            cy: Current y-coordinate of bounding box center.
            bbox_h: Height of the bounding box in pixels.
            frame_idx: Current frame number (1-indexed).
            H_ego: 3×3 homography matrix from EgoMotionEstimator,
                   or None if ego-motion couldn't be computed.
            lane_dx: Horizontal translation from ego-motion (fallback).
            lane_dy: Vertical translation from ego-motion (fallback).

        Returns:
            tuple of (status, motion_magnitude):
                - status (str): "PARKED", "MOVING", or "OUT_OF_RANGE"
                - motion_magnitude (float): Ego-compensated motion in pixels.
                  0.0 for OUT_OF_RANGE vehicles.
        """
        # ===========================================================
        # Step 1: Distance filter
        # Vehicles too far (tiny bbox) have near-zero pixel motion
        # even when driving → false PARKED. Vehicles too close
        # (huge bbox) have distorted perspective → unreliable motion.
        # ===========================================================
        if bbox_h < MIN_BBOX_HEIGHT or bbox_h > MAX_BBOX_HEIGHT:
            return "OUT_OF_RANGE", 0.0

        # ===========================================================
        # Step 2: Retrieve or initialize vehicle state
        # First time seeing this track_id → create fresh state
        # with current centroid as the starting position.
        # ===========================================================
        state = self.track_states.get(
            track_id,
            {
                "scx": cx,              # Smoothed centroid X
                "scy": cy,              # Smoothed centroid Y
                "stationary_f": 0,      # Consecutive stationary frames
                "jitter_f": 0,          # Consecutive "moving" frames (for forgiveness)
                "visible_f": 0,         # Total frames this vehicle has been seen
                "last_seen": frame_idx, # Last frame this vehicle was detected
            },
        )

        # ===========================================================
        # Step 3: EMA centroid smoothing
        # Formula: smoothed = α × current + (1-α) × previous
        #
        # With α=0.35:
        #   - 35% weight on new measurement
        #   - 65% weight on historical position
        #   - Dampens YOLO bbox jitter (typically 1-3px per frame)
        #   - A parked car's smoothed centroid moves < 0.5px/frame
        #     even if the raw bbox wobbles by 3px
        # ===========================================================
        scx = CENTROID_EMA_ALPHA * cx + (1.0 - CENTROID_EMA_ALPHA) * state["scx"]
        scy = CENTROID_EMA_ALPHA * cy + (1.0 - CENTROID_EMA_ALPHA) * state["scy"]

        # ===========================================================
        # Step 4: Ego-compensated motion computation
        #
        # Method A (preferred): Homography projection
        #   Project the previous centroid through H_ego to get where
        #   it SHOULD be this frame if it moved WITH the road surface.
        #   Difference between expected and actual = TRUE motion.
        #
        # Method B (fallback): Simple translation subtraction
        #   If homography failed (not enough lane points), subtract
        #   the average lane flow (dx, dy) from centroid displacement.
        #   Less accurate (ignores rotation/perspective) but functional.
        # ===========================================================
        if H_ego is not None:
            # Method A: Full homography projection
            pt = np.array(
                [[[state["scx"], state["scy"]]]],
                dtype=np.float32,
            )
            expected = cv2.perspectiveTransform(pt, H_ego)[0][0]
            comp_dx = scx - float(expected[0])
            comp_dy = scy - float(expected[1])
        else:
            # Method B: Simple translation fallback
            comp_dx = (scx - state["scx"]) - lane_dx
            comp_dy = (scy - state["scy"]) - lane_dy

        # Euclidean distance = total motion magnitude
        motion_magnitude = float(np.hypot(comp_dx, comp_dy))

        # ===========================================================
        # Step 5: Update stationary / jitter counters
        #
        # If motion < threshold → increment stationary counter, reset jitter
        # If motion ≥ threshold → increment jitter counter
        #   - If jitter exceeds FORGIVENESS_FRAMES → reset stationary
        #   - This prevents a single noisy frame from wiping out
        #     minutes of accumulated stationary history
        # ===========================================================
        current_threshold = self.calibrator.get_threshold()

        if motion_magnitude < current_threshold:
            state["stationary_f"] += 1
            state["jitter_f"] = 0
        else:
            state["jitter_f"] += 1
            if state["jitter_f"] > FORGIVENESS_FRAMES:
                # Genuine movement detected — reset everything
                state["stationary_f"] = 0
                state["jitter_f"] = 0

        # Update state
        state["scx"] = scx
        state["scy"] = scy
        state["visible_f"] += 1
        state["last_seen"] = frame_idx

        # ===========================================================
        # Step 6: Feed calibrator (only during first 60 frames)
        # ===========================================================
        self.calibrator.add_sample(motion_magnitude, frame_idx)

        # Save state back to dictionary
        self.track_states[track_id] = state

        # ===========================================================
        # Step 7: Final classification
        #
        # A vehicle is PARKED only if:
        #   a) It has been visible for at least MIN_VISIBLE_SECONDS
        #      (prevents ghost detections from being flagged)
        #   b) It has been continuously stationary for PARKED_SECONDS
        #      (prevents red-light stops from being flagged)
        # ===========================================================
        is_parked = (
            state["visible_f"] >= self.min_visible_frames
            and state["stationary_f"] >= self.parked_frames
        )

        status = "PARKED" if is_parked else "MOVING"
        return status, motion_magnitude

    def purge_stale_tracks(self, frame_idx: int) -> int:
        """
        Remove vehicles that haven't been seen for too long.

        Vehicles disappear from tracking when they:
            - Drive out of frame
            - Get fully occluded for too long
            - Were false detections that vanished

        Keeping their state forever would cause unbounded memory growth.
        This method deletes states older than STALE_TRACK_SECONDS.

        Args:
            frame_idx: Current frame number.

        Returns:
            int: Number of tracks purged.
        """
        stale_ids = [
            tid for tid, state in self.track_states.items()
            if frame_idx - state["last_seen"] > self.stale_track_frames
        ]

        for tid in stale_ids:
            del self.track_states[tid]

        return len(stale_ids)

    def get_active_track_count(self) -> int:
        """
        Get the number of currently active (non-purged) vehicle tracks.

        Useful for display overlay and debugging.

        Returns:
            int: Number of active tracks in memory.
        """
        return len(self.track_states)

    def reset(self) -> None:
        """
        Reset the analyzer to its initial state.

        Clears all tracked vehicles and resets the calibrator.
        Call when switching video sources or after a scene cut.
        """
        self.track_states.clear()
        self.calibrator.reset()

    def __repr__(self) -> str:
        """Readable string representation for debugging."""
        return (
            f"ParkingAnalyzer("
            f"tracks={self.get_active_track_count()}, "
            f"threshold={self.stationary_threshold:.2f}px, "
            f"calibrator={self.calibrator})"
        )
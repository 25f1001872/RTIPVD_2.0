"""
===========================================================
RTIPVD — Adaptive Threshold Calibrator
File: src/analyzer/calibrator.py
===========================================================

Auto-calibrates the stationary motion threshold based on
observed motion magnitudes during the first N frames.

WHY AUTO-CALIBRATION?
    A fixed threshold (e.g., "5 pixels") fails across different:
        - Video resolutions (720p vs 4K)
        - Camera speeds (walking vs driving at 60 kmph)
        - Camera heights (dashcam at 1.5m vs drone at 50m)
        - Lighting conditions (noise levels differ)

    Instead, we observe the scene for CALIBRATION_FRAMES (60 frames)
    and calculate what "normal motion noise" looks like for THIS
    specific video. The threshold is then set automatically.

ALGORITHM:
    1. Collect ego-compensated motion magnitudes for 60 frames
    2. Compute the 80th percentile (P80) of those values
    3. Set threshold = P80 × 1.5
    4. Clamp between MIN and MAX safety bounds

    P80 captures the boundary between "noise" and "real movement".
    The 1.5x multiplier adds a safety margin.

Pipeline position:
    Motion Analysis → [THIS MODULE provides threshold] → Parking Decision

Usage:
    from src.analyzer.calibrator import ThresholdCalibrator

    calibrator = ThresholdCalibrator()
    calibrator.add_sample(motion_magnitude, frame_idx)
    threshold = calibrator.get_threshold()
"""

import numpy as np

from config.config import (
    CALIBRATION_FRAMES,
    CALIBRATION_PERCENTILE,
    CALIBRATION_MULTIPLIER,
    MIN_STATIONARY_THRESHOLD,
    MAX_STATIONARY_THRESHOLD,
)


class ThresholdCalibrator:
    """
    Automatically calibrates the stationary motion threshold
    based on observed ego-compensated motion magnitudes.

    Lifecycle:
        1. COLLECTING: First 60 frames — samples are gathered
        2. CALIBRATING: Frame 61 — threshold is computed from samples
        3. LOCKED: Frame 62+ — threshold is fixed, no more samples

    Attributes:
        threshold (float): Current stationary threshold in pixels.
            Starts at MIN_STATIONARY_THRESHOLD, updated after calibration.
        _samples (list): Collected motion magnitudes during calibration window.
        _is_calibrated (bool): Whether calibration has been performed.
        _calibration_frames (int): Number of frames to collect samples for.
    """

    def __init__(self):
        """
        Initialize the calibrator with default (conservative) threshold.

        The initial threshold is set to MIN_STATIONARY_THRESHOLD (3.0 px).
        This is intentionally conservative — during the calibration window,
        it may cause some false "PARKED" classifications, but those early
        frames are typically ignored anyway (vehicles need MIN_VISIBLE_SECONDS
        before any parking decision is made).
        """
        self.threshold = MIN_STATIONARY_THRESHOLD
        self._samples = []
        self._is_calibrated = False
        self._calibration_frames = CALIBRATION_FRAMES

    @property
    def is_calibrated(self) -> bool:
        """Whether the calibration phase has completed."""
        return self._is_calibrated

    @property
    def sample_count(self) -> int:
        """Number of motion samples collected so far."""
        return len(self._samples)

    def add_sample(self, motion_magnitude: float, frame_idx: int) -> None:
        """
        Add a motion magnitude sample and trigger calibration if ready.

        Call this once per vehicle per frame during the calibration window.
        After CALIBRATION_FRAMES, this method automatically computes the
        threshold and locks it.

        Args:
            motion_magnitude: Ego-compensated motion magnitude (pixels).
                              This is the TRUE absolute motion of the vehicle
                              after subtracting camera ego-motion.
            frame_idx: Current frame number (1-indexed).
        """
        # Skip if already calibrated — no more samples needed
        if self._is_calibrated:
            return

        # Collect samples during the calibration window
        if frame_idx <= self._calibration_frames:
            self._samples.append(motion_magnitude)

        # Trigger calibration on the first frame after the window closes
        elif frame_idx == self._calibration_frames + 1:
            self._calibrate()

    def _calibrate(self) -> None:
        """
        Compute the stationary threshold from collected samples.

        Algorithm:
            1. Take the P80 (80th percentile) of all collected motion values
            2. Multiply by 1.5 (safety margin)
            3. Clamp between MIN and MAX thresholds

        Why P80?
            - Mean would be skewed by a few fast-moving vehicles
            - Median ignores the upper tail entirely
            - P80 captures the boundary between "noise floor" and
              "actual movement" — the sweet spot for our threshold

        Why ×1.5?
            - Adds margin so normal noise doesn't accidentally trigger
              "MOVING" classification on a truly parked vehicle

        Why clamp?
            - MIN (3.0): Prevents threshold going too low on empty roads
              (where P80 of noise ≈ 0.5 → × 1.5 = 0.75, too sensitive)
            - MAX (20.0): Prevents threshold going too high on chaotic
              scenes (where P80 ≈ 18 → × 1.5 = 27, too lenient)
        """
        if not self._samples:
            # No samples collected — keep default threshold
            self._is_calibrated = True
            return

        p_value = float(np.percentile(self._samples, CALIBRATION_PERCENTILE))

        self.threshold = float(np.clip(
            p_value * CALIBRATION_MULTIPLIER,
            MIN_STATIONARY_THRESHOLD,
            MAX_STATIONARY_THRESHOLD,
        ))

        self._is_calibrated = True

        # Free memory — samples are no longer needed after calibration
        self._samples.clear()

    def get_threshold(self) -> float:
        """
        Get the current stationary threshold.

        Returns:
            float: Threshold in pixels. Motion below this = stationary.
        """
        return self.threshold

    def reset(self) -> None:
        """
        Reset the calibrator to its initial state.

        Call this when switching video sources or after a scene cut.
        """
        self.threshold = MIN_STATIONARY_THRESHOLD
        self._samples.clear()
        self._is_calibrated = False

    def __repr__(self) -> str:
        """Readable string representation for debugging."""
        status = "CALIBRATED" if self._is_calibrated else f"COLLECTING ({self.sample_count} samples)"
        return (
            f"ThresholdCalibrator("
            f"threshold={self.threshold:.2f}px, "
            f"status={status})"
        )
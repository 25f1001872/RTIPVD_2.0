"""
===========================================================
RTIPVD — Stats Overlay
File: src/visualization/stats_overlay.py
===========================================================

Renders the real-time statistics bar at the top of the output frame.

Responsibilities:
    1. Display scene brightness level
    2. Display current stationary threshold
    3. Display ego-motion lane flow (dx, dy)
    4. Display lane pixel count (ego-motion quality metric)
    5. Display active vehicle track count
    6. Display FPS (frames per second)
    7. Display calibration status

The stats bar gives operators and evaluators instant insight into
what the system is "thinking" — making the demo self-explanatory.

Pipeline position:
    All analysis complete → [THIS MODULE] → Final display frame

Usage:
    from src.visualization.stats_overlay import StatsOverlay

    overlay = StatsOverlay()
    overlay.draw(frame, brightness, threshold, lane_dx, lane_dy,
                 lane_px_count, track_count, fps, is_calibrated)
"""

import cv2
import numpy as np
import time


class StatsOverlay:
    """
    Draws a semi-transparent stats bar at the top of the output frame.

    The bar shows real-time metrics that help understand system behavior
    during live demos and debugging sessions.

    Bar Layout:
    ┌──────────────────────────────────────────────────────────────────┐
    │ Bright: 142.3 | Thr: 5.8px | Flow: (0.42,-0.18) | Tracks: 12  │
    │ Lane: 2340px  | FPS: 24.1  | Status: CALIBRATED                │
    └──────────────────────────────────────────────────────────────────┘

    Attributes:
        _font (int): OpenCV font type.
        _font_scale (float): Font size multiplier.
        _font_thickness (int): Text stroke thickness.
        _bar_height (int): Height of the stats bar in pixels.
        _bar_color (tuple): BGR color of the bar background.
        _bar_alpha (float): Transparency of the bar background.
        _text_color (tuple): BGR color of the stats text.
        _highlight_color (tuple): BGR color for important values.
        _fps_tracker (dict): State for FPS calculation.
    """

    # Color constants
    COLOR_BAR_BG = (0, 0, 0)           # Black background
    COLOR_TEXT_PRIMARY = (255, 255, 0)  # Cyan-yellow for main stats
    COLOR_TEXT_SECONDARY = (200, 200, 200)  # Light gray for labels
    COLOR_TEXT_HIGHLIGHT = (0, 255, 255)    # Bright yellow for important values
    COLOR_TEXT_WARNING = (0, 0, 255)        # Red for warnings
    COLOR_TEXT_OK = (0, 255, 0)             # Green for good status

    def __init__(
        self,
        bar_height: int = 70,
        bar_alpha: float = 0.7,
        font_scale: float = 0.55,
        font_thickness: int = 2,
    ):
        """
        Initialize the stats overlay.

        Args:
            bar_height: Height of the stats bar in pixels.
                        70px fits two rows of text comfortably.
            bar_alpha: Transparency of the bar background.
                       0.7 is dark enough to read text but still
                       shows the video behind it.
            font_scale: Text size multiplier. 0.55 is readable at 1080p.
            font_thickness: Text stroke width.
        """
        self._font = cv2.FONT_HERSHEY_SIMPLEX
        self._font_scale = font_scale
        self._font_thickness = font_thickness
        self._bar_height = bar_height
        self._bar_alpha = bar_alpha

        # FPS tracking state
        self._prev_time = time.time()
        self._fps = 0.0
        self._fps_smoothing = 0.9  # EMA smoothing for FPS display

    def _update_fps(self) -> float:
        """
        Calculate smoothed FPS using time delta between calls.

        Uses EMA smoothing to prevent FPS display from flickering
        wildly between frames. A smoothing factor of 0.9 means
        90% of the displayed FPS comes from history.

        Returns:
            float: Smoothed FPS value.
        """
        current_time = time.time()
        delta = current_time - self._prev_time
        self._prev_time = current_time

        if delta > 0:
            instantaneous_fps = 1.0 / delta
            self._fps = (
                self._fps_smoothing * self._fps
                + (1.0 - self._fps_smoothing) * instantaneous_fps
            )

        return self._fps

    def draw(
        self,
        frame: np.ndarray,
        brightness: float = 0.0,
        threshold: float = 0.0,
        lane_dx: float = 0.0,
        lane_dy: float = 0.0,
        lane_px_count: int = 0,
        track_count: int = 0,
        is_calibrated: bool = False,
    ) -> None:
        """
        Draw the complete stats overlay bar on the frame.

        Renders a semi-transparent black bar at the top of the frame
        with two rows of real-time statistics.

        Row 1: Brightness | Threshold | Lane Flow | Tracks
        Row 2: Lane Pixels | FPS | Calibration Status

        Args:
            frame: BGR frame to draw on (modified in-place).
            brightness: Average scene brightness (0-255).
            threshold: Current stationary motion threshold (pixels).
            lane_dx: Horizontal ego-motion translation.
            lane_dy: Vertical ego-motion translation.
            lane_px_count: Number of detected lane pixels.
            track_count: Number of active vehicle tracks.
            is_calibrated: Whether threshold calibration is complete.
        """
        h, w = frame.shape[:2]
        fps = self._update_fps()

        # ----------------------------------------------------------
        # Step 1: Draw semi-transparent black bar
        # Create a black rectangle and blend it with the frame.
        # This is more visually appealing than a solid black bar.
        # ----------------------------------------------------------
        overlay = frame.copy()
        cv2.rectangle(
            overlay,
            (0, 0),
            (w, self._bar_height),
            self.COLOR_BAR_BG,
            -1,  # Filled rectangle
        )
        cv2.addWeighted(
            overlay, self._bar_alpha,
            frame, 1.0 - self._bar_alpha,
            0,
            dst=frame,
        )

        # ----------------------------------------------------------
        # Step 2: Row 1 — Primary stats
        # ----------------------------------------------------------
        row1_y = 22
        x_cursor = 15

        # Brightness
        bright_color = self.COLOR_TEXT_OK if brightness > 60 else self.COLOR_TEXT_WARNING
        row1_text = f"Bright: {brightness:.1f}"
        cv2.putText(
            frame, row1_text, (x_cursor, row1_y),
            self._font, self._font_scale, bright_color, self._font_thickness,
        )
        x_cursor += self._get_text_width(row1_text) + 20

        # Separator
        cv2.putText(
            frame, "|", (x_cursor, row1_y),
            self._font, self._font_scale, self.COLOR_TEXT_SECONDARY, 1,
        )
        x_cursor += 20

        # Threshold
        thr_text = f"Thr: {threshold:.1f}px"
        cv2.putText(
            frame, thr_text, (x_cursor, row1_y),
            self._font, self._font_scale, self.COLOR_TEXT_PRIMARY, self._font_thickness,
        )
        x_cursor += self._get_text_width(thr_text) + 20

        # Separator
        cv2.putText(
            frame, "|", (x_cursor, row1_y),
            self._font, self._font_scale, self.COLOR_TEXT_SECONDARY, 1,
        )
        x_cursor += 20

        # Lane Flow
        flow_text = f"Flow: ({lane_dx:.2f}, {lane_dy:.2f})"
        cv2.putText(
            frame, flow_text, (x_cursor, row1_y),
            self._font, self._font_scale, self.COLOR_TEXT_PRIMARY, self._font_thickness,
        )
        x_cursor += self._get_text_width(flow_text) + 20

        # Separator
        cv2.putText(
            frame, "|", (x_cursor, row1_y),
            self._font, self._font_scale, self.COLOR_TEXT_SECONDARY, 1,
        )
        x_cursor += 20

        # Active Tracks
        tracks_text = f"Tracks: {track_count}"
        cv2.putText(
            frame, tracks_text, (x_cursor, row1_y),
            self._font, self._font_scale, self.COLOR_TEXT_HIGHLIGHT, self._font_thickness,
        )

        # ----------------------------------------------------------
        # Step 3: Row 2 — Secondary stats
        # ----------------------------------------------------------
        row2_y = 50
        x_cursor = 15

        # Lane Pixel Count
        lane_color = self.COLOR_TEXT_OK if lane_px_count >= 15 else self.COLOR_TEXT_WARNING
        lane_text = f"Lane: {lane_px_count}px"
        cv2.putText(
            frame, lane_text, (x_cursor, row2_y),
            self._font, self._font_scale, lane_color, self._font_thickness,
        )
        x_cursor += self._get_text_width(lane_text) + 20

        # Separator
        cv2.putText(
            frame, "|", (x_cursor, row2_y),
            self._font, self._font_scale, self.COLOR_TEXT_SECONDARY, 1,
        )
        x_cursor += 20

        # FPS
        fps_color = self.COLOR_TEXT_OK if fps >= 15 else self.COLOR_TEXT_WARNING
        fps_text = f"FPS: {fps:.1f}"
        cv2.putText(
            frame, fps_text, (x_cursor, row2_y),
            self._font, self._font_scale, fps_color, self._font_thickness,
        )
        x_cursor += self._get_text_width(fps_text) + 20

        # Separator
        cv2.putText(
            frame, "|", (x_cursor, row2_y),
            self._font, self._font_scale, self.COLOR_TEXT_SECONDARY, 1,
        )
        x_cursor += 20

        # Calibration Status
        if is_calibrated:
            cal_text = "Status: CALIBRATED"
            cal_color = self.COLOR_TEXT_OK
        else:
            cal_text = "Status: CALIBRATING..."
            cal_color = self.COLOR_TEXT_WARNING

        cv2.putText(
            frame, cal_text, (x_cursor, row2_y),
            self._font, self._font_scale, cal_color, self._font_thickness,
        )

    def _get_text_width(self, text: str) -> int:
        """
        Calculate the pixel width of a text string.

        Used for dynamic cursor positioning so that stats
        don't overlap regardless of value lengths.

        Args:
            text: String to measure.

        Returns:
            int: Width of the text in pixels.
        """
        (text_w, _), _ = cv2.getTextSize(
            text, self._font, self._font_scale, self._font_thickness
        )
        return text_w

    def draw_simple(
        self,
        frame: np.ndarray,
        brightness: float,
        threshold: float,
    ) -> None:
        """
        Draw a minimal single-line stats bar.

        Simplified version for when you just want brightness
        and threshold without the full two-row overlay.
        Useful for quick debugging or lightweight display mode.

        Args:
            frame: BGR frame to draw on (modified in-place).
            brightness: Average scene brightness.
            threshold: Current stationary threshold.
        """
        text = f"Brightness: {brightness:.1f} | Thr: {threshold:.1f}px"
        cv2.putText(
            frame, text, (20, 30),
            self._font, 0.7, self.COLOR_TEXT_PRIMARY, 2,
        )

    def reset_fps(self) -> None:
        """Reset the FPS tracker. Call when switching video sources."""
        self._prev_time = time.time()
        self._fps = 0.0

    def __repr__(self) -> str:
        """Readable string representation for debugging."""
        return (
            f"StatsOverlay("
            f"bar_height={self._bar_height}, "
            f"alpha={self._bar_alpha}, "
            f"fps={self._fps:.1f})"
        )
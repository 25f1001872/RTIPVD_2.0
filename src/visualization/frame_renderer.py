"""
===========================================================
RTIPVD — Frame Renderer
File: src/visualization/frame_renderer.py
===========================================================

Handles all visual drawing on the output frame — bounding boxes,
labels, status text, license plate overlays, and lane mask tinting.

Responsibilities:
    1. Draw color-coded bounding boxes (Green/Red/Yellow)
    2. Render vehicle labels (ID, status, motion magnitude, plate)
    3. Apply lane mask debug overlay (green tint)
    4. Handle text background rectangles for readability

WHY SEPARATE RENDERER?
    Drawing logic was scattered across main.py — mixing detection
    code with display code. Separating it:
        - Keeps main.py clean and focused on pipeline logic
        - Allows swapping renderers (e.g., headless mode, web stream)
        - Makes it easy to add new visual elements (GPS marker, etc.)
        - Enables unit testing of rendering without running detection

COLOR CODING:
    🟢 Green  (0,255,0)   → MOVING vehicle (no concern)
    🔴 Red    (0,0,255)    → PARKED vehicle (violation flagged)
    🟡 Yellow (0,255,255)  → OUT_OF_RANGE (intentionally ignored)

Pipeline position:
    All Modules → [THIS MODULE] → cv2.imshow / Video Writer

Usage:
    from src.visualization.frame_renderer import FrameRenderer

    renderer = FrameRenderer()
    renderer.draw_vehicle(frame, x1, y1, x2, y2, track_id, status, motion, plate)
    renderer.draw_lane_overlay(frame, lane_mask)
"""

import cv2
import numpy as np


class FrameRenderer:
    """
    Draws all visual elements on the output frame.

    Encapsulates all cv2.rectangle(), cv2.putText(), and overlay
    logic into clean, callable methods. Each method modifies the
    frame in-place (numpy arrays are passed by reference).

    Attributes:
        _colors (dict): Status → BGR color mapping.
        _font (int): OpenCV font type for all text rendering.
        _font_scale (float): Base font scale for vehicle labels.
        _font_thickness (int): Text stroke thickness.
        _bbox_thickness (int): Bounding box line thickness.
        _lane_overlay_alpha (float): Transparency of lane mask overlay.
    """

    # Status → BGR color mapping
    # OpenCV uses BGR, not RGB — so Red = (0, 0, 255)
    COLOR_MOVING = (0, 255, 0)       # Green
    COLOR_PARKED = (0, 0, 255)       # Red
    COLOR_OUT_OF_RANGE = (0, 255, 255)  # Yellow
    COLOR_LABEL_BG = (0, 0, 0)       # Black background for text
    COLOR_LANE_TINT = (0, 255, 0)    # Green tint for lane overlay

    # Status string → color lookup
    _STATUS_COLORS = {
        "MOVING": COLOR_MOVING,
        "PARKED": COLOR_PARKED,
        "OUT_OF_RANGE": COLOR_OUT_OF_RANGE,
    }

    def __init__(
        self,
        font_scale: float = 0.55,
        font_thickness: int = 2,
        bbox_thickness: int = 2,
        lane_overlay_alpha: float = 0.25,
    ):
        """
        Initialize the frame renderer.

        Args:
            font_scale: Size multiplier for text labels. 0.55 works
                        well for 1080p video. Increase for 4K.
            font_thickness: Stroke width for text. 2 is readable
                            without being too thick.
            bbox_thickness: Line width for bounding box rectangles.
                            2 is visible without obscuring the vehicle.
            lane_overlay_alpha: Transparency of the green lane mask
                                overlay. 0.0 = invisible, 1.0 = opaque.
                                0.25 gives a subtle tint.
        """
        self._font = cv2.FONT_HERSHEY_SIMPLEX
        self._font_scale = font_scale
        self._font_thickness = font_thickness
        self._bbox_thickness = bbox_thickness
        self._lane_overlay_alpha = lane_overlay_alpha

    def get_status_color(self, status: str) -> tuple:
        """
        Get the BGR color for a given vehicle status.

        Args:
            status: Vehicle status string ("MOVING", "PARKED", "OUT_OF_RANGE").

        Returns:
            tuple: BGR color tuple. Defaults to Green if status is unknown.
        """
        return self._STATUS_COLORS.get(status, self.COLOR_MOVING)

    def draw_vehicle(
        self,
        frame: np.ndarray,
        x1: int, y1: int,
        x2: int, y2: int,
        track_id: int,
        status: str,
        motion_mag: float,
        plate_text: str = "",
    ) -> None:
        """
        Draw a complete vehicle annotation on the frame.

        Renders:
            1. Color-coded bounding box rectangle
            2. Label text with background: "ID:7 PARKED d=0.3"
            3. License plate text (if available): "[MH12AB1234]"

        Label format: "ID:{track_id} {status} d={motion_mag:.1f} [{plate}]"

        All drawing is done IN-PLACE on the frame (no copy created).

        Args:
            frame: BGR frame to draw on (modified in-place).
            x1, y1: Top-left corner of bounding box.
            x2, y2: Bottom-right corner of bounding box.
            track_id: Unique vehicle ID from ByteTrack.
            status: Vehicle status ("MOVING", "PARKED", "OUT_OF_RANGE").
            motion_mag: Ego-compensated motion magnitude in pixels.
            plate_text: License plate string (empty if not read yet).
        """
        color = self.get_status_color(status)

        # ----------------------------------------------------------
        # Step 1: Draw bounding box
        # ----------------------------------------------------------
        cv2.rectangle(
            frame,
            (x1, y1), (x2, y2),
            color,
            self._bbox_thickness,
        )

        # ----------------------------------------------------------
        # Step 2: Build label text
        # ----------------------------------------------------------
        label = f"ID:{track_id} {status} d={motion_mag:.1f}"
        if plate_text:
            label += f" [{plate_text}]"

        # ----------------------------------------------------------
        # Step 3: Draw label with background rectangle
        # Background makes text readable against any scene color.
        # ----------------------------------------------------------
        self._draw_label(frame, label, x1, y1, color)

    def _draw_label(
        self,
        frame: np.ndarray,
        text: str,
        x: int,
        y: int,
        color: tuple,
    ) -> None:
        """
        Draw text with a colored background rectangle above a bounding box.

        The background rectangle is sized to exactly fit the text,
        positioned just above the bounding box top edge.

        Layout:
            ┌─────────────────────┐
            │ ID:7 PARKED d=0.3   │  ← colored background
            └─────────────────────┘
            ┌─────────────────────┐
            │                     │  ← bounding box starts here
            │     Vehicle         │

        Args:
            frame: BGR frame to draw on (modified in-place).
            text: Label string to render.
            x: Left edge x-coordinate (matches bbox x1).
            y: Top edge y-coordinate of the bounding box (text goes above).
            color: BGR color for the background rectangle.
        """
        # Measure text size to create perfectly fitting background
        (text_w, text_h), baseline = cv2.getTextSize(
            text, self._font, self._font_scale, self._font_thickness
        )

        # Background rectangle: sits just above the bounding box
        padding = 4
        bg_y1 = y - text_h - padding * 2
        bg_y2 = y
        bg_x1 = x
        bg_x2 = x + text_w + padding

        # Clamp to frame boundaries
        bg_y1 = max(0, bg_y1)

        # Draw filled background rectangle
        cv2.rectangle(frame, (bg_x1, bg_y1), (bg_x2, bg_y2), color, -1)

        # Draw text on top of background (black text on colored bg)
        text_y = y - padding
        text_y = max(text_h, text_y)  # Prevent text going above frame

        cv2.putText(
            frame, text,
            (x + 2, text_y),
            self._font,
            self._font_scale,
            self.COLOR_LABEL_BG,  # Black text on colored background
            self._font_thickness,
        )

    def draw_lane_overlay(
        self,
        frame: np.ndarray,
        lane_mask: np.ndarray,
    ) -> np.ndarray:
        """
        Apply a semi-transparent green tint over detected lane pixels.

        This is a DEBUG visualization — shows which pixels the lane
        detector identified as road markings. Helps verify that:
            - Lane detection is working correctly
            - Sky/buildings are properly masked out
            - Vehicle bboxes are properly excluded

        Args:
            frame: BGR frame to overlay on (NOT modified in-place).
            lane_mask: Binary mask from LaneDetector (HxW, uint8).
                       255 = lane pixel, 0 = non-lane.

        Returns:
            np.ndarray: New BGR frame with green tint applied.
                        Original frame is NOT modified.
        """
        if lane_mask is None or np.count_nonzero(lane_mask) == 0:
            return frame

        # Create a green-only image the same size as the frame
        green_tint = np.zeros_like(frame)
        green_tint[:, :, 1] = lane_mask  # Green channel only

        # Blend: output = frame * 1.0 + green_tint * alpha
        blended = cv2.addWeighted(
            frame, 1.0,
            green_tint, self._lane_overlay_alpha,
            0,
        )

        return blended

    def draw_parked_highlight(
        self,
        frame: np.ndarray,
        x1: int, y1: int,
        x2: int, y2: int,
        pulse: bool = False,
    ) -> None:
        """
        Draw an additional highlight effect on PARKED vehicles.

        Adds a thicker outer border to make parked vehicles
        visually stand out from moving ones. Optionally supports
        a pulsing effect (alternate thickness every N frames).

        Args:
            frame: BGR frame to draw on (modified in-place).
            x1, y1: Top-left corner of bounding box.
            x2, y2: Bottom-right corner of bounding box.
            pulse: If True, draws a thicker border (for animation effect).
        """
        thickness = 4 if pulse else 3
        padding = 4

        cv2.rectangle(
            frame,
            (x1 - padding, y1 - padding),
            (x2 + padding, y2 + padding),
            self.COLOR_PARKED,
            thickness,
        )

    def __repr__(self) -> str:
        """Readable string representation for debugging."""
        return (
            f"FrameRenderer("
            f"font_scale={self._font_scale}, "
            f"bbox_thickness={self._bbox_thickness}, "
            f"lane_alpha={self._lane_overlay_alpha})"
        )
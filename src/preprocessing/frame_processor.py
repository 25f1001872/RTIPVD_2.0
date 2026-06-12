"""
===========================================================
RTIPVD — Frame Preprocessor
File: src/preprocessing/frame_processor.py
===========================================================

Handles all raw frame preprocessing before the frame enters
the detection and tracking pipeline.

Responsibilities:
    1. Optional frame resizing (for edge device deployment)
    2. Grayscale extraction (used by optical flow & lane tracker)
    3. Brightness analysis (scene awareness)
    4. Low-light enhancement via CLAHE (night mode)
    5. Color-space enhancement for YOLO under poor lighting

Pipeline position:
    VIDEO INPUT → [THIS MODULE] → Detection + Ego-Motion

Usage:
    from src.preprocessing.frame_processor import FrameProcessor

    processor = FrameProcessor(scale=1.0, night_threshold=60)
    cleaned_frame, gray, brightness = processor.process(raw_frame)
"""

import cv2
import numpy as np


class FrameProcessor:
    """
    Preprocesses raw video frames for optimal detection and tracking.

    Applies conditional enhancements based on scene brightness,
    and provides both BGR and grayscale outputs for downstream modules.

    Attributes:
        scale (float): Resize factor. 1.0 = no resize, 0.5 = half resolution.
        night_threshold (float): Brightness below this triggers CLAHE enhancement.
        clahe (cv2.CLAHE): Pre-initialized CLAHE object (avoids re-creation per frame).
        enhance_color (bool): If True, also enhances the BGR frame's luminance in low-light.
    """

    def __init__(
        self,
        scale: float = 1.0,
        night_threshold: float = 60.0,
        clahe_clip_limit: float = 2.0,
        clahe_grid_size: tuple = (8, 8),
        enhance_color: bool = False,
    ):
        """
        Initialize the frame processor.

        Args:
            scale: Resize factor for input frames. Use <1.0 on edge devices
                   (e.g., 0.5 for Raspberry Pi) to reduce compute.
                   1.0 = no resizing (recommended for RTX 4050).
            night_threshold: Average brightness threshold (0-255). Frames darker
                             than this value trigger CLAHE enhancement.
                             60 works well for typical urban night scenes.
            clahe_clip_limit: Contrast limit for CLAHE. Higher = more contrast
                              but also more noise amplification. 2.0 is standard.
            clahe_grid_size: Tile grid size for CLAHE. Smaller tiles = more local
                             contrast adaptation. (8,8) is the OpenCV default.
            enhance_color: If True, applies CLAHE to the V channel of the HSV
                           color frame as well. Helps YOLO detect in darkness
                           but adds ~2ms processing per frame.
        """
        self.scale = scale
        self.night_threshold = night_threshold
        self.enhance_color = enhance_color

        # Pre-initialize CLAHE object once (reused every frame)
        # This avoids the overhead of creating it per frame.
        self._clahe = cv2.createCLAHE(
            clipLimit=clahe_clip_limit,
            tileGridSize=clahe_grid_size,
        )

    def process(self, frame: np.ndarray) -> tuple:
        """
        Main preprocessing pipeline. Call this once per frame.

        Steps:
            1. Resize (if scale != 1.0)
            2. Convert to grayscale
            3. Measure average brightness
            4. Apply CLAHE if scene is dark (night mode)
            5. Optionally enhance color frame for YOLO

        Args:
            frame: Raw BGR frame from video capture (np.ndarray, shape HxWx3).

        Returns:
            tuple of (processed_bgr_frame, grayscale_frame, avg_brightness):
                - processed_bgr_frame (np.ndarray): BGR frame, possibly enhanced.
                - grayscale_frame (np.ndarray): Grayscale frame (CLAHE-enhanced if dark).
                - avg_brightness (float): Mean brightness of original grayscale (0-255).
        """
        # ----------------------------------------------------------
        # Step 1: Resize if needed (for edge devices / bandwidth)
        # ----------------------------------------------------------
        if self.scale != 1.0:
            frame = cv2.resize(
                frame, (0, 0),
                fx=self.scale,
                fy=self.scale,
                interpolation=cv2.INTER_LINEAR,
            )

        # ----------------------------------------------------------
        # Step 2: Extract grayscale for motion tracking & brightness
        # ----------------------------------------------------------
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # ----------------------------------------------------------
        # Step 3: Measure scene brightness
        # Brightness is used for:
        #   - Deciding whether to activate night mode
        #   - Displaying in the stats overlay bar
        # ----------------------------------------------------------
        avg_brightness = float(np.mean(gray))

        # ----------------------------------------------------------
        # Step 4: Night mode — CLAHE on grayscale
        # CLAHE (Contrast Limited Adaptive Histogram Equalization)
        # boosts local contrast in dark regions without amplifying
        # global noise. This helps optical flow find features in
        # shadows and poorly lit areas.
        # ----------------------------------------------------------
        if avg_brightness < self.night_threshold:
            gray = self._clahe.apply(gray)

            # -------------------------------------------------------
            # Step 5: Optional — enhance BGR frame for YOLO
            # Converts to HSV, applies CLAHE on the V (brightness)
            # channel, then converts back to BGR. This gives YOLO
            # a brighter, higher-contrast input in dark scenes.
            # Adds ~2ms per frame on RTX 4050.
            # -------------------------------------------------------
            if self.enhance_color:
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                hsv[:, :, 2] = self._clahe.apply(hsv[:, :, 2])
                frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        return frame, gray, avg_brightness


# =================================================================
# Backward-compatible functional API
# (So existing code using clean_frame() still works during migration)
# =================================================================

# Module-level default processor instance
_default_processor = FrameProcessor()


def clean_frame(frame: np.ndarray, scale: float = 1.0) -> tuple:
    """
    Backward-compatible wrapper around FrameProcessor.

    This function exists so that any old code doing:
        from preprocess import clean_frame
    continues to work without changes during the migration.

    For new code, prefer using the FrameProcessor class directly:
        processor = FrameProcessor(scale=1.0)
        result = processor.process(frame)

    Args:
        frame: Raw BGR frame (np.ndarray).
        scale: Resize factor (default 1.0 = no resize).

    Returns:
        tuple: (processed_frame, grayscale, avg_brightness)
    """
    global _default_processor

    # Update scale if it differs from default
    if _default_processor.scale != scale:
        _default_processor = FrameProcessor(scale=scale)

    return _default_processor.process(frame)
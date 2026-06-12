"""
===========================================================
RTIPVD — Lane Detector
File: src/ego_motion/lane_detector.py
===========================================================

Detects road lane markings using HSV color filtering and
edge validation to create a binary mask of road-surface features.

Responsibilities:
    1. Isolate white (and optionally yellow) lane markings via HSV
    2. Reject false positives (sky, buildings, sun glare) using:
       - Horizon masking (top 50% of frame ignored)
       - Canny edge intersection (flat bright blobs rejected)
       - Morphological cleanup (small noise removed)
    3. Mask out vehicle bounding boxes (prevent car body edges
       from being mistaken as lane features)

WHY LANE MARKINGS?
    Lane markings are PAINTED ON THE ROAD SURFACE. Their apparent
    motion in the video = exact camera-to-road motion. Unlike
    buildings/trees (which have parallax due to varying depth),
    lane markings share the same plane as the vehicles — making
    them the ideal ego-motion reference anchor.

Pipeline position:
    PREPROCESSED FRAME → [THIS MODULE] → Motion Estimator → Analyzer

Usage:
    from src.ego_motion.lane_detector import LaneDetector

    lane_det = LaneDetector()
    mask, pixel_count = lane_det.detect(frame, vehicle_boxes)
"""

import cv2
import numpy as np

from config.config import (
    WHITE_HSV_LO,
    WHITE_HSV_HI,
    HORIZON_RATIO,
    VEHICLE_MASK_PADDING,
)


class LaneDetector:
    """
    Detects road lane markings and produces a binary mask.

    The mask is used downstream by MotionEstimator to seed
    optical flow feature points exclusively on the road surface.

    Attributes:
        _kernel (np.ndarray): Morphological kernel, pre-created once.
    """

    def __init__(self):
        """
        Initialize the lane detector.

        Pre-creates the morphological kernel to avoid per-frame overhead.
        """
        # 3x3 rectangular kernel for edge dilation and morphological opening.
        # Rectangle shape works well for lane markings which are elongated.
        self._kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

    def detect(self, frame: np.ndarray, vehicle_boxes) -> tuple:
        """
        Generate a binary mask of detected lane markings.

        Pipeline:
            1. HSV color filter → isolate white lane pixels
            2. Horizon mask → zero out top portion (sky/buildings)
            3. Canny edge intersection → reject flat bright blobs
            4. Morphological opening → remove small noise
            5. Vehicle bbox mask → prevent car edges leaking in

        Args:
            frame: BGR frame from video (np.ndarray, shape HxWx3).
            vehicle_boxes: YOLO detection boxes (result.boxes) or None.
                           Used to blank out vehicle regions from the mask.

        Returns:
            tuple of (lane_mask, lane_pixel_count):
                - lane_mask (np.ndarray): Binary mask, same size as frame,
                  where 255 = lane pixel, 0 = non-lane.
                - lane_pixel_count (int): Total number of non-zero pixels
                  in the mask. Used to decide if enough features exist.
        """
        h, w = frame.shape[:2]

        # ----------------------------------------------------------
        # Step 1: HSV Color Filter
        # Convert BGR → HSV and threshold for white lane markings.
        # HSV is preferred over RGB because it separates brightness
        # from color — so white lanes stay detectable even in shadows.
        # ----------------------------------------------------------
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, WHITE_HSV_LO, WHITE_HSV_HI)

        # ----------------------------------------------------------
        # Step 2: Horizon Mask
        # Zero out the top portion of the frame. Everything above
        # the horizon line is sky, buildings, trees — not road.
        # HORIZON_RATIO = 0.5 means top 50% is ignored.
        # ----------------------------------------------------------
        horizon_y = int(h * HORIZON_RATIO)
        mask[0:horizon_y, :] = 0

        # ----------------------------------------------------------
        # Step 3: Canny Edge Intersection
        # Lane markings have sharp edges. Sun glare and bright
        # building walls are flat (no edges inside them).
        # By AND-ing the color mask with an edge map, we keep
        # only bright regions that also have strong gradients.
        #
        # Process:
        #   a) Canny edge detection on grayscale
        #   b) Dilate edges slightly (so they overlap with color mask)
        #   c) Bitwise AND → only color pixels near edges survive
        # ----------------------------------------------------------
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edges = cv2.dilate(edges, self._kernel, iterations=1)
        mask = cv2.bitwise_and(mask, edges)

        # ----------------------------------------------------------
        # Step 4: Morphological Opening
        # Removes small isolated noise blobs (1-2 pixel clusters)
        # that survived the color + edge filters. Opening = erosion
        # followed by dilation — shrinks small blobs to nothing,
        # then expands surviving regions back to original size.
        # ----------------------------------------------------------
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel)

        # ----------------------------------------------------------
        # Step 5: Vehicle Bounding Box Masking
        # Zero out regions occupied by detected vehicles. Without
        # this, the edge of a white car could be mistaken for a
        # lane marking — corrupting the ego-motion estimate.
        #
        # A padding of VEHICLE_MASK_PADDING pixels is added around
        # each bbox to account for slight detection inaccuracies.
        # ----------------------------------------------------------
        if vehicle_boxes is not None:
            for box in vehicle_boxes:
                bx1, by1, bx2, by2 = map(int, box.xyxy[0])
                pad = VEHICLE_MASK_PADDING

                # Clamp coordinates to frame boundaries
                y_start = max(0, by1 - pad)
                y_end = min(h, by2 + pad)
                x_start = max(0, bx1 - pad)
                x_end = min(w, bx2 + pad)

                mask[y_start:y_end, x_start:x_end] = 0

        # Count remaining lane pixels
        lane_pixel_count = int(np.count_nonzero(mask))

        return mask, lane_pixel_count

    def __repr__(self) -> str:
        """Readable string representation for debugging."""
        return (
            f"LaneDetector("
            f"horizon={HORIZON_RATIO}, "
            f"padding={VEHICLE_MASK_PADDING})"
        )
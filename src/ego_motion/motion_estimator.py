"""
===========================================================
RTIPVD — Ego-Motion Estimator
File: src/ego_motion/motion_estimator.py
===========================================================

Estimates camera ego-motion (how much the camera itself moved)
using optical flow on lane marking features detected by LaneDetector.

Responsibilities:
    1. Seed trackable feature points on lane marking pixels
    2. Track those points across frames using Lucas-Kanade optical flow
    3. Compute a RANSAC homography matrix from the point correspondences
    4. Extract translation (dx, dy) from the homography
    5. Manage feature point lifecycle (seed → track → re-seed)

WHY THIS MATTERS:
    On a moving camera, a parked car appears to move in the video.
    By computing the camera's own motion (ego-motion) from road-surface
    features, we can subtract it from each vehicle's apparent motion
    to get their TRUE absolute motion.

    TRUE MOTION = Vehicle's apparent motion − Camera ego-motion

    If TRUE MOTION ≈ 0 for N seconds → vehicle is PARKED.

KEY ALGORITHMS:
    - Lucas-Kanade (LK) Optical Flow:
        Sparse flow algorithm. Tracks selected points from frame N to
        frame N+1 by comparing local pixel windows. Fast because it
        only processes selected points, not every pixel.

    - RANSAC Homography:
        Computes a 3×3 transformation matrix from point correspondences.
        RANSAC (Random Sample Consensus) makes it robust to outliers —
        even if 30-40% of matches are wrong, the result is still correct.
        The homography captures translation, rotation, scale, AND
        perspective warp — not just simple horizontal shift.

Pipeline position:
    Lane Detector → [THIS MODULE] → Parking Analyzer

Usage:
    from src.ego_motion.lane_detector import LaneDetector
    from src.ego_motion.motion_estimator import EgoMotionEstimator

    lane_det = LaneDetector()
    estimator = EgoMotionEstimator()

    mask, px_count = lane_det.detect(frame, boxes)
    H_ego, dx, dy, px_count = estimator.compute(gray, mask, px_count)
"""

import cv2
import numpy as np

from config.config import (
    MAX_LANE_FEATURES,
    MIN_LANE_FEATURES,
)


class EgoMotionEstimator:
    """
    Computes camera ego-motion using sparse optical flow on lane features.

    Maintains state across frames:
        - Previous grayscale frame (for LK flow computation)
        - Previous feature points (carried over or re-seeded)

    The estimator outputs:
        - H_ego: 3×3 homography matrix (full perspective transform)
        - dx, dy: Translation components extracted from H_ego
        - lane_pixel_count: Number of lane pixels detected (quality metric)

    Attributes:
        max_features (int): Maximum feature points to track per frame.
        min_features (int): Minimum points needed for reliable homography.
        _prev_gray (np.ndarray): Grayscale frame from the previous iteration.
        _prev_pts (np.ndarray): Feature points tracked from the previous frame.

    Lucas-Kanade Parameters (hardcoded — rarely need tuning):
        qualityLevel=0.01: Accept even low-quality corners (lanes are subtle).
        minDistance=10: Minimum 10px between feature points (avoid clustering).
    """

    # LK optical flow parameters — shared across all instances.
    # These are OpenCV defaults tuned for road-surface tracking.
    _LK_PARAMS = dict(
        winSize=(15, 15),       # Search window size
        maxLevel=2,             # Pyramid levels (handles multi-scale motion)
        criteria=(              # Termination criteria
            cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
            10,     # Max iterations
            0.03,   # Epsilon (convergence threshold)
        ),
    )

    # goodFeaturesToTrack parameters
    _GFT_QUALITY = 0.01    # Accept low-quality corners (lane markings are subtle)
    _GFT_MIN_DIST = 10     # Minimum pixel distance between features

    # RANSAC reprojection threshold for homography (pixels)
    _RANSAC_THRESH = 3.0

    # Minimum point correspondences required for homography computation.
    # cv2.findHomography needs at least 4, but more = more robust.
    _MIN_HOMOGRAPHY_POINTS = 4

    def __init__(
        self,
        max_features: int = MAX_LANE_FEATURES,
        min_features: int = MIN_LANE_FEATURES,
    ):
        """
        Initialize the ego-motion estimator.

        Args:
            max_features: Maximum number of feature points to track.
                          More points = more robust homography but slower.
                          2500 is a good balance for RTX 4050.
            min_features: Minimum lane feature points required for
                          reliable ego-motion computation. Below this,
                          the system falls back to generic background
                          features (or returns no homography).
        """
        self.max_features = max_features
        self.min_features = min_features

        # Frame-to-frame state
        self._prev_gray = None
        self._prev_pts = None

    def compute(
        self,
        current_gray: np.ndarray,
        lane_mask: np.ndarray,
        lane_pixel_count: int,
    ) -> tuple:
        """
        Compute ego-motion between the previous frame and the current frame.

        Algorithm:
            1. Check if previous frame exists (skip first frame)
            2. Re-seed feature points if too few are being tracked
            3. Run Lucas-Kanade optical flow (prev → current)
            4. Filter to only successfully tracked points
            5. Compute RANSAC homography from correspondences
            6. Extract dx, dy translation from the homography matrix
            7. Carry over good points for the next frame
            8. Update state (store current gray as previous)

        Args:
            current_gray: Grayscale of the current frame (np.ndarray, HxW).
            lane_mask: Binary mask from LaneDetector (np.ndarray, HxW).
                       Feature points are seeded ONLY on white pixels.
            lane_pixel_count: Number of non-zero pixels in lane_mask.
                              Used to decide if lane-based seeding is viable.

        Returns:
            tuple of (H_ego, dx, dy, lane_pixel_count):
                - H_ego (np.ndarray or None): 3×3 homography matrix.
                  None if insufficient points or first frame.
                - dx (float): Horizontal translation component of ego-motion.
                - dy (float): Vertical translation component of ego-motion.
                - lane_pixel_count (int): Pass-through of the input count
                  (for display in stats overlay).
        """
        H_ego = None
        dx, dy = 0.0, 0.0

        if self._prev_gray is not None:
            # ----------------------------------------------------------
            # Step 1: Re-seed feature points if running low
            # Points get lost over time due to occlusion, frame edges,
            # or tracking failures. When count drops below min_features,
            # we re-seed from the lane mask (or generic if no lanes).
            # ----------------------------------------------------------
            if self._prev_pts is None or len(self._prev_pts) < self.min_features:
                self._prev_pts = self._seed_features(
                    self._prev_gray, lane_mask, lane_pixel_count
                )

            # ----------------------------------------------------------
            # Step 2: Run Lucas-Kanade optical flow
            # Tracks each point from prev_gray → current_gray.
            # Returns new positions (curr_pts) and a status array
            # indicating which points were successfully tracked.
            # ----------------------------------------------------------
            if self._prev_pts is not None and len(self._prev_pts) >= self._MIN_HOMOGRAPHY_POINTS:
                curr_pts, status, _ = cv2.calcOpticalFlowPyrLK(
                    self._prev_gray,
                    current_gray,
                    self._prev_pts,
                    None,
                    **self._LK_PARAMS,
                )

                # Keep only successfully tracked points
                good_prev = self._prev_pts[status.ravel() == 1]
                good_curr = curr_pts[status.ravel() == 1]

                # ----------------------------------------------------------
                # Step 3: Compute RANSAC homography
                # Maps the road plane from prev frame → current frame.
                # RANSAC automatically rejects outlier correspondences.
                #
                # The resulting H_ego matrix tells us:
                # "If a point was at position P in the previous frame,
                #  where would it be in the current frame if it is
                #  stationary on the road surface?"
                #
                # H_ego[0,2] = horizontal translation (dx)
                # H_ego[1,2] = vertical translation (dy)
                # Full matrix also captures rotation and perspective.
                # ----------------------------------------------------------
                if len(good_prev) >= self._MIN_HOMOGRAPHY_POINTS:
                    H_ego, inlier_mask = cv2.findHomography(
                        good_prev, good_curr,
                        cv2.RANSAC,
                        self._RANSAC_THRESH,
                    )

                    if H_ego is not None:
                        dx = float(H_ego[0, 2])
                        dy = float(H_ego[1, 2])

                # ----------------------------------------------------------
                # Step 4: Carry over good points for next frame
                # Avoids re-seeding every frame (expensive). Only re-seed
                # when tracked points drop below min_features.
                # ----------------------------------------------------------
                if len(good_curr) >= self.min_features:
                    self._prev_pts = good_curr.reshape(-1, 1, 2)
                else:
                    self._prev_pts = None
            else:
                # Not enough points to track — will re-seed next frame
                self._prev_pts = None

        # ----------------------------------------------------------
        # Step 5: Store current frame as previous for next iteration
        # .copy() is critical — without it, both _prev_gray and
        # current_gray would point to the same numpy array, and
        # when the caller modifies the frame, _prev_gray changes too.
        # ----------------------------------------------------------
        self._prev_gray = current_gray.copy()

        return H_ego, dx, dy, lane_pixel_count

    def _seed_features(
        self,
        gray: np.ndarray,
        lane_mask: np.ndarray,
        lane_pixel_count: int,
    ) -> np.ndarray:
        """
        Find new feature points to track.

        Seeding strategy:
            - If enough lane pixels exist → seed ON lane mask only.
              This gives us pure road-surface features.
            - If too few lane pixels → seed without mask (generic background).
              Less accurate but prevents total ego-motion failure.

        Args:
            gray: Grayscale frame to extract features from.
            lane_mask: Binary mask of lane markings.
            lane_pixel_count: Number of non-zero pixels in lane_mask.

        Returns:
            np.ndarray or None: Array of feature points (Nx1x2),
            or None if no features found.
        """
        # Use lane mask only if enough lane pixels are available.
        # Otherwise fall back to generic features (no mask).
        use_mask = lane_mask if lane_pixel_count >= self.min_features else None

        points = cv2.goodFeaturesToTrack(
            gray,
            maxCorners=self.max_features,
            qualityLevel=self._GFT_QUALITY,
            minDistance=self._GFT_MIN_DIST,
            mask=use_mask,
        )

        return points

    def reset(self):
        """
        Reset the estimator's state.

        Call this when switching video sources or after a scene cut.
        Clears the previous frame and tracked points so the estimator
        starts fresh without comparing to an unrelated frame.
        """
        self._prev_gray = None
        self._prev_pts = None

    def __repr__(self) -> str:
        """Readable string representation for debugging."""
        pts_count = len(self._prev_pts) if self._prev_pts is not None else 0
        return (
            f"EgoMotionEstimator("
            f"tracking={pts_count} pts, "
            f"max={self.max_features}, "
            f"min={self.min_features})"
        )
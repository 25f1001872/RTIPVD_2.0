# Parking Detection System Explanation

This document explains the logic and inner workings of the `parking_detection.py` script. The script is designed to detect parked vehicles in a video stream, even if the camera itself is moving (e.g., a dashcam or moving drone). 

## Overview

The system uses a combination of object detection, object tracking, and optical flow for ego-motion compensation. The main pipeline is as follows:
1. **Object Detection & Tracking:** Uses a YOLO model to detect and track vehicles across frames.
2. **Lane Detection:** Isolates white and yellow lane markings on the road.
3. **Ego-motion Compensation:** Tracks the movement of lane features between frames to calculate how the camera moved relative to the road.
4. **Motion Analysis:** Compares the tracked vehicle motion against the camera motion to determine their true motion on the ground.
5. **State Classification:** Classifies a vehicle as `PARKED`, `MOVING`, or `FAR` based on its true motion and distance.

---

## 1. Object Detection and Tracking
The script uses `ultralytics YOLO` to detect vehicles and track them (`model.track(...)`). 
It filters detections using the `is_vehicle_label` function, which maps specific classes (like car, truck, bus, bike) to valid targets. The tracker assigns a unique ID to each detected vehicle, allowing the script to follow them over time.

---

## 2. Lane Masking for Road Reference
Because the camera might be moving, just looking at a vehicle's bounding box movement in the video is not enough to know if it's parked. A parked car will look like it's moving across the screen if the camera turns. 

To solve this, the script uses the road as an anchor:
- **`get_lane_mask(...)`:** Converts the frame to HSV color space and isolates white and yellow colors, representing painted road lane lines.
- **Masking Vehicles out:** It masks out the bounding boxes of detected vehicles so that the ego-motion tracker doesn't latch onto a moving car accidentally.

---

## 3. Ego-Motion Tracking (Lucas-Kanade)
To calculate how much the camera moved:
- **Feature Extraction:** It finds trackable points in the road/lane mask using `cv2.goodFeaturesToTrack`.
- **Optical Flow:** It tracks these points from the previous frame to the current frame using `cv2.calcOpticalFlowPyrLK`.
- **Homography Calculation:** Using `cv2.findHomography`, it computes a transformation matrix (`H_ego`) that describes the overall perspective shift and translation of the road surface between frames.

---

## 4. Centroid Smoothing and True Motion
For every tracked vehicle:
- **Centroid Calculation:** Finds the center of the bounding box.
- **EMA Smoothing (`CENTROID_EMA_ALPHA`):** Applies Exponential Moving Average (EMA) to the centroid coordinates to reduce bounding box jitter. Bounding boxes often shrink or expand slightly every frame; EMA dampens this noise.
- **Compensated Motion:** The script takes the vehicle's position from the *previous* frame and projects it using the road's homography matrix (`H_ego`) into the current frame. This tells us: *where would this vehicle be in the current frame if it had exactly zero motion relative to the road?*
- The difference between this expected position and its actual smoothed position is its **true absolute motion**.

---

## 5. Thresholds and Calibration
The script computes if the true motion is small enough to be considered "stationary".
- **Auto-calibration:** During the first `CALIBRATION_FRAMES` (e.g., 60 frames), it records all tracked motion vectors to calculate a baseline threshold (`stationary_threshold`), making it adaptable to different video resolutions and scenes.
- **Distance Filter:** Vehicles whose bounding box height is below `MIN_BBOX_HEIGHT` (default 60 pixels) are marked as `FAR`. They are skipped for parked logic because vehicles far away have tiny motion vectors that look similar whether they are driving or parked.

---

## 6. Keeping State and Output
The `track_state` dictionary maintains the history for each vehicle ID:
- It tracks how many consecutive frames the vehicle has been stationary (`stationary_frames`).
- **Forgiveness Frames:** If a parked car has a sudden 1-frame jitter spike, it isn't immediately reset to MOVING, thanks to `FORGIVENESS_FRAMES`.
- **Classification:** If a vehicle is visible long enough and has been stationary for `PARKED_SECONDS`, it is drawn with a red bounding box and labeled `PARKED`. Otherwise, it is labeled `MOVING`.
- **Cleanup:** It deletes state for vehicles that haven't been seen for `STALE_TRACK_SECONDS`.

Finally, it overlays all text and bounding boxes on the output frame and displays it.
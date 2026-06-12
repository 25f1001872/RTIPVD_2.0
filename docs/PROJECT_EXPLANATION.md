# RTIPVD: Full Project Explanation

## 1. Project Purpose

RTIPVD (Real-Time Illegal Parking Vehicle Detection) is a computer-vision system that identifies illegally parked vehicles from moving-camera video (dashcam, patrol, drone-like motion), extracts license plates, tags geospatial coordinates, stores incidents, and optionally syncs them to a backend API.

Primary entrypoint: `main.py`

High-level summary: `README.md`

## 2. What the System Does

RTIPVD combines several tasks in one pipeline:

- Vehicle detection and multi-object tracking (YOLOv8 + ByteTrack)
- Ego-motion compensation so moving camera footage can still detect truly parked vehicles
- Parking decision logic with adaptive thresholds
- Plate OCR with temporal voting for stability
- Evidence persistence in local SQLite
- Optional backend sync through REST
- Optional geofencing using GeoJSON no-parking zones
- Optional Pi-to-laptop streaming mode with frame + GPS telemetry

## 3. Operating Modes

### A. Local Processing Mode

Runs full detection locally from a video source through `main.py`.

Main modules used:

- `src/preprocessing/frame_processor.py`
- `src/detection/vehicle_detector.py`
- `src/detection/vehicle_tracker.py`
- `src/ego_motion/lane_detector.py`
- `src/ego_motion/motion_estimator.py`
- `src/analyzer/parking_analyzer.py`
- `src/ocr/plate_reader.py`
- `src/evidence/violation_service.py`
- `src/visualization/frame_renderer.py`
- `src/visualization/stats_overlay.py`

### B. Distributed Streaming Mode (Recommended Deployment Direction)

Raspberry Pi acts as sender, laptop acts as processing server.

Sender side:

- `deploy/raspberry_pi/send_video_and_gps.py`
- `deploy/raspberry_pi/send_stream.sh`

Receiver/processor side:

- `scripts/laptop_stream_server.py`

Supporting docs:

- `docs/BEGINNER_GUIDE.md`
- `docs/STREAMING_ARCHITECTURE.md`

## 4. Core Pipeline Explained

Per-frame logic in `main.py` follows this sequence:

1. Frame preprocessing
   - `src/preprocessing/frame_processor.py` computes grayscale, brightness, and low-light enhancement with CLAHE.

2. Vehicle detection + tracking
   - `src/detection/vehicle_detector.py` loads YOLO and validates classes as vehicles.
   - `src/detection/vehicle_tracker.py` provides persistent track IDs using ByteTrack.

3. Lane-based ego-motion estimation
   - `src/ego_motion/lane_detector.py` isolates lane-like pixels and masks vehicles out.
   - `src/ego_motion/motion_estimator.py` tracks lane features via Lucas-Kanade optical flow and computes homography.

4. Parking decision
   - `src/analyzer/parking_analyzer.py` computes ego-compensated motion and classifies each track as MOVING, PARKED, or OUT_OF_RANGE.

5. OCR for parked vehicles only
   - `src/ocr/plate_detector.py` extracts the plate region.
   - `src/ocr/plate_reader.py` runs EasyOCR and temporal voting.

6. Evidence persistence and optional sync
   - `src/evidence/violation_service.py` records incidents to DB and optionally posts to backend.

7. Visualization and operator overlay
   - `src/visualization/frame_renderer.py` draws boxes and labels.
   - `src/visualization/stats_overlay.py` shows runtime metrics.

## 5. Why Ego-Motion Compensation Matters

With a moving camera, even parked vehicles appear to move in pixel space. RTIPVD estimates camera motion from lane features and subtracts it from each tracked vehicle's apparent motion.

Conceptually:

- Apparent vehicle motion = vehicle motion + camera motion effects
- Estimated true vehicle motion = apparent motion - estimated camera motion

Parking decisions are made from this compensated motion, not raw centroid drift.

## 6. Parking Decision Logic

Implemented in `src/analyzer/parking_analyzer.py` and `src/analyzer/calibrator.py`.

Key features:

- Bounding-box size filter rejects too-far and too-close detections
- EMA smoothing reduces detector jitter
- Adaptive threshold calibration during initial frames
- Forgiveness window avoids flipping parked vehicles to moving due to short spikes
- Time-based parked classification using FPS-scaled thresholds

Main tunable thresholds are centralized in `config/config.py`.

## 7. OCR Strategy

Implemented in `src/ocr/plate_reader.py`.

Design choices:

- OCR runs only for PARKED status, reducing compute
- Regex validation for expected plate format
- Per-track history window with majority voting to stabilize noisy frame-by-frame OCR
- Mock OCR mode supported via config for fast testing

## 8. Geospatial and Illegal Zone Logic

Geospatial projection:

- `src/geospatial/vehicle_geo_mapper.py`

Zone checking:

- `src/geospatial/zone_checker.py`

Flow:

- Camera GPS + heading + detection bbox produce estimated vehicle lat/lon
- Optional GeoJSON zone check can restrict persistence to configured no-parking areas

## 9. Data and Persistence

Models:

- `src/database/models.py`

Database operations:

- `src/database/db_manager.py`

Schema:

- `src/database/migrations/init_schema.sql`

The `violations` table stores:

- Plate
- First/last seen timestamps
- Duration
- Lat/lon
- Screenshot path (optional)
- Video source and confidence

Upsert behavior merges near-contiguous observations of the same plate within a merge window.

## 10. Backend API and Dashboard

Backend server:

- `dashboard/backend/app.py`
- `dashboard/backend/routes.py`

Endpoints:

- `GET /api/health`
- `GET /api/violations?limit=100`
- `POST /api/violations`

Frontend dashboard:

- `dashboard/frontend/index.html`
- `dashboard/frontend/app.js`
- `dashboard/frontend/styles.css`

The dashboard polls health and recent violations for operator visibility.

## 11. Streaming Telemetry Contract

Packet model:

- `src/streaming/packet.py`

GPS synchronization:

- `src/streaming/sync.py`

Each frame packet contains:

- `sequence_id`
- `frame_timestamp_utc`
- `gps` object
- `frame_jpeg_base64`

On laptop, packet GPS is used first; if missing or invalid, nearest timestamped fix from the sync buffer is used.

## 12. Configuration System

Central configuration:

- `config/config.py`

Highlights:

- Uses `RTIPVD_*` environment variables with defaults
- Resolves project-relative paths safely
- Controls device, model/video paths, thresholds, OCR, DB, backend, stream transport, and geofencing
- Supports profile-based behavior for laptop vs Pi

Examples:

- `deploy/laptop/laptop.env.example`
- `deploy/raspberry_pi/pi.env.example`

## 13. Deployment and Launchers

Laptop:

- `deploy/laptop/run_laptop.ps1`
- `deploy/laptop/start_backend.ps1`
- `deploy/laptop/start_stream_server.ps1`
- `deploy/laptop/README.md`

Raspberry Pi:

- `deploy/raspberry_pi/setup.sh`
- `deploy/raspberry_pi/run_pi.sh`
- `deploy/raspberry_pi/send_stream.sh`
- `deploy/raspberry_pi/upload_from_windows.ps1`
- `deploy/raspberry_pi/README.md`

## 14. Setup and Utility Scripts

- `scripts/verify_setup.py`: checks environment, files, and imports
- `scripts/calculate_vehicle_geocoords.py`: offline geospatial CSV generation
- `scripts/download_weights.py`: fallback weight download if custom model is missing

## 15. Outputs Produced

Typical output locations:

- `output/db`: local SQLite databases
- `output/violations`: violation artifacts
- `output/results/stream_geocoords.csv`: streaming geospatial records
- `output/results`: additional CSV outputs

## 16. Current Gaps and Placeholder Areas

Several planned files currently exist as placeholders (empty), indicating roadmap space rather than completed implementation:

- `tests/test_database.py`
- `tests/test_detection.py`
- `tests/test_ego_motion.py`
- `tests/test_parking_analyzer.py`
- `tests/test_plate_reader.py`
- `scripts/convert_model.py`
- `scripts/generate_report.py`
- `deploy/docker/Dockerfile`
- `deploy/docker/docker-compose.yml`
- `deploy/jetson_nano/optimize_model.py`
- `deploy/jetson_nano/setup.sh`
- `dashboard/templates/base.html`

## 17. Packaging and Dependencies

Packaging:

- `pyproject.toml`
- `setup.py`

Dependencies:

- `requirements.txt`
- `dashboard/backend/requirements.txt`

Core libraries include Ultralytics YOLO, OpenCV, EasyOCR, Flask, requests, and pyserial.

## 18. Practical End-to-End Flow Summary

In deployment mode:

1. Pi captures frame and GPS, then sends packet.
2. Laptop receives packet and runs detection/tracking.
3. Ego-motion compensation estimates true vehicle motion.
4. Parked vehicles trigger OCR and violation recording.
5. Geospatial estimate is computed per detection.
6. DB is updated locally and backend sync is attempted if enabled.
7. Dashboard serves latest violations via API.

This design keeps the edge sender lightweight while concentrating compute-heavy inference on the laptop/server.

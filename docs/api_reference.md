# RTIPVD — API Reference

## Module Overview

### `src.preprocessing.FrameProcessor`
```python
processor = FrameProcessor(scale=1.0, night_threshold=60.0)
frame, gray, brightness = processor.process(raw_frame)
```

### `src.detection.VehicleDetector`
```python
detector = VehicleDetector(model_path="weights/best.pt", device="cuda:0")
is_car = detector.is_vehicle(cls_id=2)
label = detector.get_label(cls_id=2)
```

### `src.detection.VehicleTracker`
```python
tracker = VehicleTracker(detector, tracker_config="config/bytetrack.yaml")
for result in tracker.stream(source="video.mp4"):
    boxes = result.boxes
```

### `src.ego_motion.LaneDetector`
```python
lane_det = LaneDetector()
mask, pixel_count = lane_det.detect(frame, vehicle_boxes)
```

### `src.ego_motion.EgoMotionEstimator`
```python
estimator = EgoMotionEstimator()
H_ego, dx, dy, px_count = estimator.compute(gray, lane_mask, px_count)
```

### `src.analyzer.ParkingAnalyzer`
```python
analyzer = ParkingAnalyzer(fps=30.0)
status, motion = analyzer.analyze_vehicle(
    track_id, cx, cy, bbox_h, frame_idx, H_ego, dx, dy
)
analyzer.purge_stale_tracks(frame_idx)
```

### `src.analyzer.ThresholdCalibrator`
```python
calibrator = ThresholdCalibrator()
calibrator.add_sample(motion_magnitude, frame_idx)
threshold = calibrator.get_threshold()
```

### `src.ocr.PlateReader`
```python
reader = PlateReader(use_mock=False)
plate_text = reader.read(frame, x1, y1, x2, y2, track_id)
```

### `src.visualization.FrameRenderer`
```python
renderer = FrameRenderer()
renderer.draw_vehicle(frame, x1, y1, x2, y2, track_id, status, motion, plate)
frame = renderer.draw_lane_overlay(frame, lane_mask)
```

### `src.visualization.StatsOverlay`
```python
overlay = StatsOverlay()
overlay.draw(frame, brightness, threshold, lane_dx, lane_dy, px_count, tracks, calibrated)
```
"""
Calculate detected vehicle geospatial coordinates from a local video.

This utility runs YOLO detection on each frame and projects detections
into latitude/longitude using the camera's own GPS position.
"""

import argparse
import csv
from pathlib import Path

import cv2

from src.detection.vehicle_detector import VehicleDetector
from src.geospatial.vehicle_geo_mapper import VehicleGeoMapper


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute vehicle geospatial estimates from video")
    parser.add_argument("--video", required=True, help="Path to input video")
    parser.add_argument("--model", default="weights/best.pt", help="Path to YOLO model")
    parser.add_argument("--camera-lat", type=float, required=True, help="Camera latitude")
    parser.add_argument("--camera-lon", type=float, required=True, help="Camera longitude")
    parser.add_argument("--camera-heading", type=float, default=0.0, help="Camera heading in degrees")
    parser.add_argument("--hfov", type=float, default=78.0, help="Camera horizontal field of view")
    parser.add_argument("--output", default="output/results/vehicle_geocoords.csv", help="CSV output path")
    parser.add_argument("--conf", type=float, default=0.30, help="Detection confidence threshold")
    parser.add_argument("--device", default="cpu", help="Inference device (cpu/cuda:0)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    video_path = Path(args.video)
    if not video_path.exists():
        print(f"[ERROR] Video not found: {video_path}")
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    detector = VehicleDetector(model_path=args.model, device=args.device)
    model = detector.get_model()
    mapper = VehicleGeoMapper(horizontal_fov_deg=args.hfov)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"[ERROR] Cannot open video: {video_path}")
        return 1

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "frame_idx",
                "timestamp_sec",
                "class_id",
                "class_label",
                "bbox_x1",
                "bbox_y1",
                "bbox_x2",
                "bbox_y2",
                "camera_lat",
                "camera_lon",
                "camera_heading_deg",
                "vehicle_lat",
                "vehicle_lon",
                "distance_m",
                "bearing_deg",
                "geo_confidence",
                "det_confidence",
            ]
        )

        frame_idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            frame_idx += 1
            frame_h, frame_w = frame.shape[:2]
            timestamp_sec = frame_idx / fps

            results = model.predict(
                source=frame,
                conf=args.conf,
                verbose=False,
                device=args.device,
            )

            if not results:
                continue

            boxes = results[0].boxes
            if boxes is None:
                continue

            for box in boxes:
                cls_id = int(box.cls[0])
                if not detector.is_vehicle(cls_id):
                    continue

                x1, y1, x2, y2 = map(float, box.xyxy[0])
                det_conf = float(box.conf[0]) if box.conf is not None else 0.0

                estimate = mapper.estimate_from_bbox(
                    camera_lat=args.camera_lat,
                    camera_lon=args.camera_lon,
                    camera_heading_deg=args.camera_heading,
                    bbox_xyxy=(x1, y1, x2, y2),
                    frame_shape=(frame_h, frame_w),
                )
                if estimate is None:
                    continue

                writer.writerow(
                    [
                        frame_idx,
                        round(timestamp_sec, 3),
                        cls_id,
                        detector.get_label(cls_id),
                        round(x1, 2),
                        round(y1, 2),
                        round(x2, 2),
                        round(y2, 2),
                        args.camera_lat,
                        args.camera_lon,
                        args.camera_heading,
                        round(estimate.latitude, 8),
                        round(estimate.longitude, 8),
                        round(estimate.distance_m, 3),
                        round(estimate.bearing_deg, 3),
                        round(estimate.confidence, 3),
                        round(det_conf, 3),
                    ]
                )

    cap.release()
    print(f"[DONE] Geospatial detections saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

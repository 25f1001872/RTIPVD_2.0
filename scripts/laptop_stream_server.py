"""
Laptop stream server for RTIPVD.

Receives frame+GPS packets from Raspberry Pi and runs the full
moving-camera pipeline on the laptop:

- YOLO + ByteTrack tracking
- Ego-motion compensation + parked/moving classification
- OCR for parked vehicles
- Violation persistence (SQLite) + optional backend sync
- Geospatial CSV logging for detections
"""

import atexit
import argparse
import csv
from pathlib import Path
import sys
from threading import Lock
from typing import Dict, List


import cv2
from flask import Flask, jsonify, request

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import (
    BACKEND_API_KEY,
    BACKEND_ENABLED,
    BACKEND_TIMEOUT_SEC,
    BACKEND_URL,
    BACKEND_VERIFY_SSL,
    DB_ENABLED,
    DB_PATH,
    DEBUG_LANE_OVERLAY,
    GEO_MAPPER_HFOV_DEG,
    ILLEGAL_PARKING_DEFAULT_HEADING_DEG,
    ILLEGAL_PARKING_GEOJSON_ENABLED,
    ILLEGAL_PARKING_GEOJSON_PATH,
    TRACKER_CONFIG,
    USE_MOCK_OCR,
    WINDOW_NAME,
    GPS_MOCK_LAT,
    GPS_MOCK_LON,
)
from src.analyzer.parking_analyzer import ParkingAnalyzer
from src.database.backend_client import BackendClient
from src.database.db_manager import DatabaseManager
from src.database.models import GPSFix
from src.detection.vehicle_detector import VehicleDetector
from src.ego_motion.lane_detector import LaneDetector
from src.ego_motion.motion_estimator import EgoMotionEstimator
from src.evidence.violation_service import ViolationService
from src.geospatial.vehicle_geo_mapper import VehicleGeoMapper
from src.geospatial.zone_checker import NoParkingZoneChecker
from src.ocr.plate_reader import PlateReader
from src.preprocessing.frame_processor import FrameProcessor
from src.streaming.packet import FrameTelemetryPacket
from src.streaming.ops_state import OpsStateStore
from src.streaming.sync import GPSSyncBuffer
from src.visualization.frame_renderer import FrameRenderer
from src.visualization.stats_overlay import StatsOverlay


def _resolve_path(path_value: str) -> str:
    path = Path(path_value)
    if path.is_absolute():
        return str(path)
    return str((PROJECT_ROOT / path).resolve())


class StreamPacketGPSTagger:
    """GPS adapter that feeds packet GPS fixes into ViolationService."""

    def __init__(self, default_heading_deg: float):
        self._latest_fix = GPSFix(
            latitude=None,
            longitude=None,
            heading_deg=default_heading_deg,
            speed_mps=None,
            satellites=None,
            fix=False,
            source="stream",
        )

    @property
    def is_ready(self) -> bool:
        return True

    def update_fix(self, gps_fix: GPSFix) -> None:
        self._latest_fix = gps_fix

    def get_latest(self) -> GPSFix:
        return self._latest_fix

    def close(self) -> None:
        return

    def __repr__(self) -> str:
        return f"StreamPacketGPSTagger(source='{self._latest_fix.source}')"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RTIPVD laptop stream processor")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8088, help="Bind port")
    parser.add_argument("--model", default="weights/best.pt", help="YOLO model path")
    parser.add_argument("--device", default="cpu", help="Inference device")
    parser.add_argument("--tracker-config", default=TRACKER_CONFIG, help="ByteTrack YAML path")
    parser.add_argument("--det-conf", type=float, default=0.30, help="Detection confidence")
    parser.add_argument("--det-iou", type=float, default=0.50, help="Detection IoU threshold")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size")
    parser.add_argument("--input-fps", type=float, default=8.0, help="Expected incoming FPS")
    
    parser.add_argument("--hfov", type=float, default=GEO_MAPPER_HFOV_DEG, help="Camera horizontal FOV")
    #New arguments for geospatial mapping
    parser.add_argument("--utm-zone", type=int, default=44, help="UTM zone for coordinate conversion (Dehradun is 44)")
    parser.add_argument(
        "--default-heading",
        type=float,
        default=ILLEGAL_PARKING_DEFAULT_HEADING_DEG,
        help="Fallback heading (degrees)",
    )
    parser.add_argument("--log-csv", default="output/results/stream_geocoords.csv", help="Output CSV for detections")

    parking_group = parser.add_mutually_exclusive_group()
    parking_group.add_argument("--enable-parking", dest="enable_parking", action="store_true")
    parking_group.add_argument("--disable-parking", dest="enable_parking", action="store_false")
    parser.set_defaults(enable_parking=True)

    parser.add_argument("--use-mock-ocr", action="store_true", default=USE_MOCK_OCR, help="Use mock OCR")

    parser.add_argument("--db-path", default=DB_PATH, help="SQLite path for violations")
    parser.add_argument("--disable-db", action="store_true", default=not DB_ENABLED, help="Disable local DB writes")

    parser.add_argument("--backend-enabled", action="store_true", default=BACKEND_ENABLED, help="Enable backend sync")
    parser.add_argument("--backend-url", default=BACKEND_URL, help="Backend API URL")
    parser.add_argument("--backend-api-key", default=BACKEND_API_KEY, help="Backend API key")
    parser.add_argument("--backend-timeout-sec", type=float, default=BACKEND_TIMEOUT_SEC, help="Backend timeout")
    parser.add_argument(
        "--backend-skip-ssl-verify",
        action="store_true",
        default=not BACKEND_VERIFY_SSL,
        help="Disable SSL verification for backend sync",
    )

    zone_group = parser.add_mutually_exclusive_group()
    zone_group.add_argument("--zone-enabled", dest="zone_enabled", action="store_true")
    zone_group.add_argument("--zone-disabled", dest="zone_enabled", action="store_false")
    parser.set_defaults(zone_enabled=ILLEGAL_PARKING_GEOJSON_ENABLED)
    parser.add_argument("--zone-geojson", default=ILLEGAL_PARKING_GEOJSON_PATH, help="No-parking zones GeoJSON")

    display_group = parser.add_mutually_exclusive_group()
    display_group.add_argument("--show-display", dest="show_display", action="store_true")
    display_group.add_argument("--hide-display", dest="show_display", action="store_false")
    parser.set_defaults(show_display=False)

    lane_overlay_group = parser.add_mutually_exclusive_group()
    lane_overlay_group.add_argument("--debug-lane-overlay", dest="debug_lane_overlay", action="store_true")
    lane_overlay_group.add_argument("--no-debug-lane-overlay", dest="debug_lane_overlay", action="store_false")
    parser.set_defaults(debug_lane_overlay=DEBUG_LANE_OVERLAY)

    parser.add_argument("--window-name", default=WINDOW_NAME, help="OpenCV display window name")

    args = parser.parse_args()
    args.model = _resolve_path(args.model)
    args.tracker_config = _resolve_path(args.tracker_config)
    args.log_csv = _resolve_path(args.log_csv)
    args.db_path = _resolve_path(args.db_path)
    args.zone_geojson = _resolve_path(args.zone_geojson)
    return args


def _build_app(args: argparse.Namespace) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
    process_lock = Lock()
    frame_idx = 0

    detector = VehicleDetector(model_path=args.model, device=args.device)
    model = detector.get_model()
    preprocessor = FrameProcessor()
    lane_detector = LaneDetector()
    ego_estimator = EgoMotionEstimator()
    analyzer = ParkingAnalyzer(fps=max(float(args.input_fps), 1.0))
    plate_reader = PlateReader(use_mock=args.use_mock_ocr)
    renderer = FrameRenderer()
    overlay = StatsOverlay()

    packet_gps_tagger = StreamPacketGPSTagger(default_heading_deg=args.default_heading)

    db_manager = DatabaseManager(
        db_path=args.db_path,
        enabled=not args.disable_db,
    )
    backend_client = BackendClient(
        enabled=args.backend_enabled,
        url=args.backend_url,
        api_key=args.backend_api_key,
        timeout_sec=args.backend_timeout_sec,
        verify_ssl=not args.backend_skip_ssl_verify,
    )

    mapper = VehicleGeoMapper(horizontal_fov_deg=args.hfov)
    zone_checker = NoParkingZoneChecker(
        enabled=args.zone_enabled,
        geojson_path=args.zone_geojson,
    )
    violation_service = ViolationService(
        db_manager=db_manager,
        gps_tagger=packet_gps_tagger,
        backend_client=backend_client,
        video_source=f"stream://{args.host}:{args.port}",
        geo_mapper=mapper,
        zone_checker=zone_checker,
        default_heading_deg=args.default_heading,
    )

    if zone_checker.enabled and not zone_checker.is_ready:
        print(
            "[STREAM SERVER] WARNING: Geofence enabled but no zones were loaded. "
            f"Check GeoJSON path: {args.zone_geojson}"
        )
    if zone_checker.enabled and zone_checker.is_ready:
        print(
            f"[STREAM SERVER] Geofence active with {zone_checker.zone_count} zone(s): "
            f"{zone_checker.geojson_path}"
        )

    gps_sync = GPSSyncBuffer(max_size=1024)
    ops_store = OpsStateStore()

    csv_path = Path(args.log_csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    stats: Dict[str, int] = {
        "packets_received": 0,
        "frames_processed": 0,
        "detections_logged": 0,
        "violations_upserted": 0,
        "inference_errors": 0,
        "csv_write_errors": 0,
        "last_track_count": 0,
        "last_parked_count": 0,
    }

    if not csv_path.exists():
        with csv_path.open("w", newline="", encoding="utf-8") as fp:
            writer = csv.writer(fp)
            writer.writerow(
                [
                    "sequence_id",
                    "frame_timestamp_utc",
                    "track_id",
                    "status",
                    "plate_text",
                    "violation_id",
                    "class_id",
                    "class_label",
                    "bbox_x1",
                    "bbox_y1",
                    "bbox_x2",
                    "bbox_y2",
                    "motion_px",
                    "camera_lat",
                    "camera_lon",
                    "camera_heading",
                    "vehicle_lat",
                    "vehicle_lon",
                    "distance_m",
                    "bearing_deg",
                    "geo_confidence",
                    "det_confidence",
                ]
            )

    def _has_usable_coords(gps_fix: GPSFix) -> bool:
        if gps_fix.latitude is None or gps_fix.longitude is None:
            return False
        try:
            lat = float(transform_coordinate(gps_fix.latitude))
            lon = float(transform_coordinate(gps_fix.longitude))
        except (TypeError, ValueError):
            return False
        # Treat (0, 0) as a placeholder/no-fix coordinate for stream processing.
        if abs(lat) < 1e-9 and abs(lon) < 1e-9:
            return False
        return True

    def _resolve_gps(packet: FrameTelemetryPacket) -> GPSFix:
        parsed_fix = gps_sync.parse_fix(packet.gps)
        lat = parsed_fix.latitude
        lon = parsed_fix.longitude
        if parsed_fix.fix and _has_usable_coords(parsed_fix):
            parsed_fix.latitude = lat
            parsed_fix.longitude = lon
            gps_sync.add_fix(parsed_fix)
            return parsed_fix
        # Some senders may provide valid coordinates but omit or mis-set the fix flag.
        # Accept these as best-effort coordinates for projection.
        if (not parsed_fix.fix) and _has_usable_coords(parsed_fix):
            coords_only = GPSFix(
                latitude=lat,
                longitude=lon,
                satellites=parsed_fix.satellites,
                heading_deg=parsed_fix.heading_deg,
                speed_mps=parsed_fix.speed_mps,
                fix=True,
                source=f"{parsed_fix.source}:coords_only",
                timestamp=parsed_fix.timestamp,
            )
            gps_sync.add_fix(coords_only)
            return coords_only
        matched = gps_sync.get_closest(packet.frame_timestamp_utc)
        if matched is not None:
            return matched
        return GPSFix(
            latitude=None,
            longitude=None,
            heading_deg=None,
            speed_mps=None,
            satellites=None,
            fix=False,
            source="unsynced",
            timestamp=parsed_fix.timestamp,
        )

    def _process_packet(packet: FrameTelemetryPacket) -> List[dict]:
        nonlocal frame_idx

        frame = packet.decode_frame()
        if frame is None:
            return []

        frame_idx += 1
        stats["frames_processed"] += 1

        gps_fix = _resolve_gps(packet)
        packet_gps_tagger.update_fix(gps_fix)

        has_camera_fix = (
            gps_fix.fix
            and gps_fix.latitude is not None
            and gps_fix.longitude is not None
        )

        cam_lat = float(gps_fix.latitude) if gps_fix.latitude is not None else float(GPS_MOCK_LAT)
        cam_lon = float(gps_fix.longitude) if gps_fix.longitude is not None else float(GPS_MOCK_LON)

        heading = gps_fix.heading_deg if gps_fix.heading_deg is not None else args.default_heading

        try:
            results = model.track(
                source=frame,
                tracker=args.tracker_config,
                persist=True,
                conf=args.det_conf,
                iou=args.det_iou,
                imgsz=args.imgsz,
                verbose=False,
                device=args.device,
            )
        except Exception as exc:
            stats["inference_errors"] += 1
            print(f"[STREAM SERVER] WARN inference failed on seq={packet.sequence_id}: {exc}")
            return []

        if not results:
            return []

        result = results[0]
        boxes = result.boxes
        orig_frame = result.orig_img.copy() if getattr(result, "orig_img", None) is not None else frame.copy()

        cleaned_frame, gray, avg_brightness = preprocessor.process(orig_frame)
        display_frame = cleaned_frame.copy()

        lane_mask, lane_px_count = lane_detector.detect(cleaned_frame, boxes)
        H_ego, lane_dx, lane_dy, _ = ego_estimator.compute(gray, lane_mask, lane_px_count)

        if args.debug_lane_overlay and args.show_display:
            display_frame = renderer.draw_lane_overlay(display_frame, lane_mask)

        frame_h, frame_w = cleaned_frame.shape[:2]

        write_fp = None
        writer = None
        try:
            write_fp = csv_path.open("a", newline="", encoding="utf-8")
            writer = csv.writer(write_fp)
        except PermissionError:
            stats["csv_write_errors"] += 1
            writer = None

        detections: List[dict] = []
        parked_count = 0
        active_track_ids = set()
        read_plates: Dict[int, str] = {}
        parked_for_ops: List[dict] = []

        if boxes is not None:
            for box in boxes:
                cls_id = int(box.cls[0])
                track_id = int(box.id[0]) if box.id is not None else -1

                if track_id < 0 or not detector.is_vehicle(cls_id):
                    continue

                active_track_ids.add(track_id)

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                det_conf = float(box.conf[0]) if box.conf is not None else 0.0

                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0
                bbox_h = y2 - y1

                status, motion_mag = analyzer.analyze_vehicle(
                    track_id=track_id,
                    cx=cx,
                    cy=cy,
                    bbox_h=bbox_h,
                    frame_idx=frame_idx,
                    H_ego=H_ego,
                    lane_dx=lane_dx,
                    lane_dy=lane_dy,
                )

                plate_text = ""
                violation_id = None

                if args.enable_parking and status == "PARKED":
                    parked_count += 1
                    if track_id not in read_plates:
                        read_plates[track_id] = plate_reader.read(orig_frame, x1, y1, x2, y2, track_id)
                    plate_text = read_plates[track_id]

                    violation_id = violation_service.report_parked(
                        track_id=track_id,
                        plate_text=plate_text,
                        frame_idx=frame_idx,
                        confidence=det_conf,
                        bbox_xyxy=(x1, y1, x2, y2),
                        frame_shape=orig_frame.shape[:2],
                    )
                    if violation_id is not None:
                        stats["violations_upserted"] += 1

                estimate = mapper.estimate_from_bbox(
                    camera_lat=cam_lat,
                    camera_lon=cam_lon,
                    camera_heading_deg=float(heading),
                    bbox_xyxy=(float(x1), float(y1), float(x2), float(y2)),
                    frame_shape=(frame_h, frame_w),
                )

                parking_status = "LEGAL"
                zone_id = None
                zone_name = None
                if status == "PARKED" and zone_checker is not None and zone_checker.enabled:
                    zone_match = zone_checker.find_zone(
                        estimate.latitude if estimate is not None else None,
                        estimate.longitude if estimate is not None else None,
                    )
                    if zone_match is not None:
                        parking_status = "ILLEGAL"
                        zone_id = zone_match.zone_id
                        zone_name = zone_match.zone_name

                row = {
                    "sequence_id": packet.sequence_id,
                    "frame_timestamp_utc": packet.frame_timestamp_utc,
                    "track_id": track_id,
                    "status": status,
                    "parking_status": parking_status,
                    "zone_id": zone_id,
                    "zone_name": zone_name,
                    "plate_text": plate_text,
                    "violation_id": violation_id,
                    "class_id": cls_id,
                    "class_label": detector.get_label(cls_id),
                    "bbox": [x1, y1, x2, y2],
                    "motion_px": motion_mag,
                    "camera_lat": cam_lat,
                    "camera_lon": cam_lon,
                    "camera_heading": heading,
                    "vehicle_lat": estimate.latitude if estimate is not None else None,
                    "vehicle_lon": estimate.longitude if estimate is not None else None,
                    "distance_m": estimate.distance_m if estimate is not None else None,
                    "bearing_deg": estimate.bearing_deg if estimate is not None else None,
                    "geo_confidence": estimate.confidence if estimate is not None else None,
                    "det_confidence": det_conf,
                }
                detections.append(row)
                stats["detections_logged"] += 1

                if status == "PARKED":
                    parked_for_ops.append(
                        {
                            "track_id": track_id,
                            "plate_text": plate_text,
                            "parking_status": parking_status,
                            "latitude": row["vehicle_lat"],
                            "longitude": row["vehicle_lon"],
                            "confidence": det_conf,
                            "bbox": [x1, y1, x2, y2],
                        }
                    )

                if writer is not None:
                    writer.writerow(
                        [
                            packet.sequence_id,
                            packet.frame_timestamp_utc,
                            track_id,
                            status,
                            plate_text,
                            violation_id,
                            cls_id,
                            detector.get_label(cls_id),
                            x1,
                            y1,
                            x2,
                            y2,
                            round(motion_mag, 3),
                            cam_lat,
                            cam_lon,
                            round(float(heading), 3),
                            round(estimate.latitude, 8) if estimate is not None else None,
                            round(estimate.longitude, 8) if estimate is not None else None,
                            round(estimate.distance_m, 3) if estimate is not None else None,
                            round(estimate.bearing_deg, 3) if estimate is not None else None,
                            round(estimate.confidence, 3) if estimate is not None else None,
                            round(det_conf, 3),
                        ]
                    )

                if args.show_display:
                    renderer.draw_vehicle(
                        display_frame,
                        x1,
                        y1,
                        x2,
                        y2,
                        track_id,
                        status,
                        motion_mag,
                        plate_text,
                    )
                    if status == "PARKED":
                        renderer.draw_parked_highlight(
                            display_frame,
                            x1,
                            y1,
                            x2,
                            y2,
                            pulse=(frame_idx % 20 < 10),
                        )

        track_ids_before = set(analyzer.track_states.keys())
        purged_count = analyzer.purge_stale_tracks(frame_idx)
        track_ids_after = set(analyzer.track_states.keys())
        purged_track_ids = track_ids_before - track_ids_after

        if purged_count > 0:
            for tid in purged_track_ids:
                plate_reader.clear_track(tid)

        if args.enable_parking:
            violation_service.close_inactive_tracks(track_ids_after)

        stats["last_track_count"] = analyzer.get_active_track_count()
        stats["last_parked_count"] = parked_count

        if args.show_display:
            overlay.draw(
                display_frame,
                brightness=avg_brightness,
                threshold=analyzer.stationary_threshold,
                lane_dx=lane_dx,
                lane_dy=lane_dy,
                lane_px_count=lane_px_count,
                track_count=analyzer.get_active_track_count(),
                is_calibrated=analyzer.calibrator.is_calibrated,
            )
            cv2.imshow(args.window_name, display_frame)
            cv2.waitKey(1)

        if write_fp is not None:
            write_fp.close()

        gps_timestamp = None
        if getattr(gps_fix, "timestamp", None) is not None:
            gps_timestamp = gps_fix.timestamp.isoformat()

        ops_store.update_frame(display_frame, packet.sequence_id, jpeg_quality=65)
        ops_store.update_gps(
            {
                "latitude": cam_lat,
                "longitude": cam_lon,
                "heading_deg": heading,
                "speed_mps": gps_fix.speed_mps,
                "satellites": gps_fix.satellites,
                "fix": gps_fix.fix,
                "source": gps_fix.source,
                "timestamp": gps_timestamp,
            }
        )
        ops_store.update_plates(parked_for_ops, orig_frame=orig_frame)

        return detections

    def _cleanup() -> None:
        try:
            violation_service.close()
        except Exception:
            pass
        if args.show_display:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass

    atexit.register(_cleanup)

    @app.get("/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "stats": stats,
                "model": args.model,
                "device": args.device,
                "csv_log": str(csv_path),
                "db_path": str(args.db_path),
                "parking_enabled": args.enable_parking,
                "display_enabled": args.show_display,
            }
        )

    @app.get("/ops/state")
    def ops_state():
        return jsonify(ops_store.get_state())

    @app.post("/ingest/frame")
    def ingest_frame():
        payload = request.get_json(silent=True)
        if not payload:
            return jsonify({"ok": False, "error": "Empty or invalid JSON"}), 400

        try:
            packet = FrameTelemetryPacket.from_json(payload)
        except Exception as exc:
            return jsonify({"ok": False, "error": f"Bad payload: {exc}"}), 400

        stats["packets_received"] += 1

        with process_lock:
            detections = _process_packet(packet)

        return jsonify(
            {
                "ok": True,
                "sequence_id": packet.sequence_id,
                "detections": detections,
                "detection_count": len(detections),
            }
        )

    return app


def main() -> int:
    args = parse_args()
    app = _build_app(args)
    print(f"[STREAM SERVER] Listening on http://{args.host}:{args.port}")
    print(f"[STREAM SERVER] CSV log: {args.log_csv}")
    print(f"[STREAM SERVER] Parking mode: {'enabled' if args.enable_parking else 'disabled'}")
    print(
        f"[STREAM SERVER] Geofence: {'enabled' if args.zone_enabled else 'disabled'} "
        f"({args.zone_geojson})"
    )
    print(f"[STREAM SERVER] DB: {'enabled' if not args.disable_db else 'disabled'} ({args.db_path})")
    print(f"[STREAM SERVER] Display: {'enabled' if args.show_display else 'disabled'}")
    app.run(host=args.host, port=args.port, debug=False, threaded=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

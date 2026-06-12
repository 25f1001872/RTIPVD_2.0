"""
RTIPVD violation service.

Coordinates GPS tagging, local SQLite persistence, and
optional backend API sync for parked vehicle incidents.
"""

from datetime import timedelta
from typing import Dict, Iterable, Optional, Tuple
from config.config import ILLEGAL_PARKING_DEFAULT_HEADING_DEG, GPS_MOCK_LAT, GPS_MOCK_LON

from src.database.backend_client import BackendClient
from src.database.db_manager import DatabaseManager
from src.database.models import ViolationRecord, utc_now
from src.evidence.gps_tagger import GPSTagger
from src.geospatial.vehicle_geo_mapper import VehicleGeoMapper
from src.geospatial.zone_checker import NoParkingZoneChecker


class ViolationService:
    """High-level helper to record and sync parked-vehicle violations."""

    DETECTING_TEXT = "DETECTING..."

    def __init__(
        self,
        db_manager: DatabaseManager,
        gps_tagger: GPSTagger,
        backend_client: BackendClient,
        video_source: str,
        min_report_interval_frames: int = 5,
        geo_mapper: Optional[VehicleGeoMapper] = None,
        zone_checker: Optional[NoParkingZoneChecker] = None,
        default_heading_deg: float = ILLEGAL_PARKING_DEFAULT_HEADING_DEG,
    ):
        self.db_manager = db_manager
        self.gps_tagger = gps_tagger
        self.backend_client = backend_client
        self.video_source = video_source
        self.min_report_interval_frames = max(1, int(min_report_interval_frames))
        self.geo_mapper = geo_mapper
        self.zone_checker = zone_checker
        self.default_heading_deg = float(default_heading_deg)

        self._active_tracks: Dict[int, Dict[str, object]] = {}

    def report_parked(
        self,
        track_id: int,
        plate_text: str,
        frame_idx: int,
        confidence: Optional[float] = None,
        bbox_xyxy: Optional[Tuple[int, int, int, int]] = None,
        frame_shape: Optional[Tuple[int, int]] = None,
    ) -> Optional[int]:
        """Persist one parked observation and optionally sync it to backend."""
        plate = (plate_text or "").strip().upper()
        if not plate:
            return None

        if plate == self.DETECTING_TEXT:
            return None

        state = self._active_tracks.get(track_id)
        now = utc_now()

        if state is None or state.get("plate") != plate:
            state = {
                "plate": plate,
                "first_seen": now,
                "last_sync_frame": -1,
                "violation_id": None,
                "last_seen": now,
            }
            self._active_tracks[track_id] = state

        if frame_idx - int(state["last_sync_frame"]) < self.min_report_interval_frames:
            state["last_seen"] = now
            return state.get("violation_id")

        gps_fix = self.gps_tagger.get_latest()
        latitude, longitude = self._estimate_vehicle_coordinates(
            gps_fix=gps_fix,
            bbox_xyxy=bbox_xyxy,
            frame_shape=frame_shape,
        )

        # If geofence checking is enabled, classify each parked record as
        # ILLEGAL (inside a zone) or LEGAL (outside all zones).
        zone_match = None
        if self.zone_checker is not None and self.zone_checker.enabled:
            zone_match = self.zone_checker.find_zone(latitude, longitude)
        parking_status = "ILLEGAL" if zone_match is not None else "LEGAL"

        first_seen = state.get("first_seen", now)
        duration = max((now - first_seen).total_seconds(), 0.0)

        record = ViolationRecord(
            license_plate=plate,
            first_seen=first_seen,
            last_seen=now,
            duration_sec=duration,
            latitude=latitude,
            longitude=longitude,
            screenshot_path=None,
            video_source=self.video_source,
            confidence=confidence,
            parking_status=parking_status,
            zone_id=zone_match.zone_id if zone_match is not None else None,
            zone_name=zone_match.zone_name if zone_match is not None else None,
        )

        violation_id, inserted = self.db_manager.upsert_violation(record)
        state["last_sync_frame"] = frame_idx
        state["violation_id"] = violation_id
        state["last_seen"] = now

        if violation_id is not None:
            event_type = "created" if inserted else "updated"
            if zone_match is not None:
                print(
                    f"[ViolationService] Illegal parking in zone '{zone_match.zone_name}' "
                    f"(zone_id={zone_match.zone_id}) for plate={plate}"
                )
            self.backend_client.send_violation(
                record,
                violation_id=violation_id,
                event_type=event_type,
            )

        return violation_id

    def _estimate_vehicle_coordinates(
        self,
        gps_fix,
        bbox_xyxy: Optional[Tuple[int, int, int, int]],
        frame_shape: Optional[Tuple[int, int]],
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Estimate vehicle coordinates from camera GPS + detection box.

        Fallback order:
            1) Vehicle geolocation via VehicleGeoMapper (preferred)
            2) Camera GPS coordinates (if available)
            3) None, None when no fix is available
        """
        cam_lat = float(gps_fix.latitude) if gps_fix.latitude is not None else float(GPS_MOCK_LAT)
        cam_lon = float(gps_fix.longitude) if gps_fix.longitude is not None else float(GPS_MOCK_LON)

        if self.geo_mapper is None or bbox_xyxy is None or frame_shape is None:
            return cam_lat, cam_lon

        frame_h, frame_w = frame_shape
        heading = (
            float(gps_fix.heading_deg)
            if gps_fix.heading_deg is not None
            else self.default_heading_deg
        )

        estimate = self.geo_mapper.estimate_from_bbox(
            camera_lat=cam_lat,
            camera_lon=cam_lon,
            camera_heading_deg=heading,
            bbox_xyxy=tuple(map(float, bbox_xyxy)),
            frame_shape=(int(frame_h), int(frame_w)),
        )
        if estimate is None:
            return cam_lat, cam_lon

        return float(estimate.latitude), float(estimate.longitude)

    def close_inactive_tracks(self, active_track_ids: Iterable[int]) -> int:
        """Drop local state for tracks that disappeared and send final sync."""
        active_set = set(active_track_ids)
        stale_ids = [tid for tid in self._active_tracks.keys() if tid not in active_set]

        for track_id in stale_ids:
            state = self._active_tracks.pop(track_id)
            violation_id = state.get("violation_id")
            if violation_id is None:
                continue

            row = self.db_manager.get_violation(int(violation_id))
            if row is None:
                continue

            record = ViolationRecord.from_db_row(row)
            # Mark final sighting a little later than last seen to avoid zero-duration edges.
            record.last_seen = record.last_seen + timedelta(milliseconds=1)
            self.backend_client.send_violation(
                record,
                violation_id=int(violation_id),
                event_type="closed",
            )

        return len(stale_ids)

    def close(self) -> None:
        """Release all owned resources."""
        self.gps_tagger.close()
        self.backend_client.close()
        self.db_manager.close()

    def __repr__(self) -> str:
        return (
            "ViolationService("
            f"active_tracks={len(self._active_tracks)}, "
            f"db_ready={self.db_manager.is_ready}, "
            f"gps_ready={self.gps_tagger.is_ready}, "
            f"backend_ready={self.backend_client.is_ready}, "
            f"geo_mapper={'on' if self.geo_mapper is not None else 'off'}, "
            f"zone_checker={'on' if (self.zone_checker is not None and self.zone_checker.enabled) else 'off'})"
        )

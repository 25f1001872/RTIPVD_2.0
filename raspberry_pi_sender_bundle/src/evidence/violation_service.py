"""
RTIPVD violation service.

Coordinates GPS tagging, local SQLite persistence, and
optional backend API sync for parked vehicle incidents.
"""

from datetime import timedelta
from typing import Dict, Iterable, Optional

from src.database.backend_client import BackendClient
from src.database.db_manager import DatabaseManager
from src.database.models import ViolationRecord, utc_now
from src.evidence.gps_tagger import GPSTagger


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
    ):
        self.db_manager = db_manager
        self.gps_tagger = gps_tagger
        self.backend_client = backend_client
        self.video_source = video_source
        self.min_report_interval_frames = max(1, int(min_report_interval_frames))

        self._active_tracks: Dict[int, Dict[str, object]] = {}

    def report_parked(
        self,
        track_id: int,
        plate_text: str,
        frame_idx: int,
        confidence: Optional[float] = None,
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
        first_seen = state.get("first_seen", now)
        duration = max((now - first_seen).total_seconds(), 0.0)

        record = ViolationRecord(
            license_plate=plate,
            first_seen=first_seen,
            last_seen=now,
            duration_sec=duration,
            latitude=gps_fix.latitude if gps_fix.fix else None,
            longitude=gps_fix.longitude if gps_fix.fix else None,
            screenshot_path=None,
            video_source=self.video_source,
            confidence=confidence,
        )

        violation_id, inserted = self.db_manager.upsert_violation(record)
        state["last_sync_frame"] = frame_idx
        state["violation_id"] = violation_id
        state["last_seen"] = now

        if violation_id is not None:
            event_type = "created" if inserted else "updated"
            self.backend_client.send_violation(
                record,
                violation_id=violation_id,
                event_type=event_type,
            )

        return violation_id

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
            f"backend_ready={self.backend_client.is_ready})"
        )

"""Shared live operations state for dashboard/console polling."""

import base64
import copy
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

import cv2


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class OpsStateStore:
    """Thread-safe singleton store for live operations data."""

    _instance: Optional["OpsStateStore"] = None
    _instance_guard = Lock()

    def __new__(cls) -> "OpsStateStore":
        with cls._instance_guard:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_state()
        return cls._instance

    def _init_state(self) -> None:
        self._lock = Lock()
        self._state: Dict[str, Any] = {
            "ok": True,
            "updated_at_utc": _utc_now_iso(),
            "frame": {
                "sequence_id": None,
                "image_b64": None,
                "width": None,
                "height": None,
                "updated_at_utc": None,
            },
            "gps": {
                "latitude": None,
                "longitude": None,
                "heading_deg": None,
                "speed_mps": None,
                "satellites": None,
                "fix": False,
                "source": "stream",
                "timestamp": None,
                "updated_at_utc": None,
            },
            "plates": [],
        }

    def update_frame(self, frame_bgr, sequence_id: int, jpeg_quality: int = 65) -> None:
        if frame_bgr is None:
            return

        quality = int(max(35, min(int(jpeg_quality), 95)))
        ok, encoded = cv2.imencode(
            ".jpg",
            frame_bgr,
            [int(cv2.IMWRITE_JPEG_QUALITY), quality],
        )
        if not ok:
            return

        now = _utc_now_iso()
        image_b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
        height, width = frame_bgr.shape[:2]

        with self._lock:
            self._state["frame"] = {
                "sequence_id": int(sequence_id),
                "image_b64": image_b64,
                "width": int(width),
                "height": int(height),
                "updated_at_utc": now,
            }
            self._state["updated_at_utc"] = now

    def update_gps(self, gps_payload: Dict[str, Any]) -> None:
        payload = dict(gps_payload or {})
        now = _utc_now_iso()

        gps_state = {
            "latitude": _safe_float(payload.get("latitude")),
            "longitude": _safe_float(payload.get("longitude")),
            "heading_deg": _safe_float(payload.get("heading_deg")),
            "speed_mps": _safe_float(payload.get("speed_mps")),
            "satellites": payload.get("satellites"),
            "fix": bool(payload.get("fix", False)),
            "source": str(payload.get("source") or "stream"),
            "timestamp": payload.get("timestamp") or now,
            "updated_at_utc": now,
        }

        with self._lock:
            self._state["gps"] = gps_state
            self._state["updated_at_utc"] = now

    def update_plates(self, parked_plates: List[Dict[str, Any]], orig_frame=None) -> None:
        now = _utc_now_iso()
        normalized: List[Dict[str, Any]] = []

        for plate in list(parked_plates or [])[:2]:
            bbox_raw = plate.get("bbox") or []
            bbox: List[int] = []
            if isinstance(bbox_raw, (list, tuple)) and len(bbox_raw) == 4:
                try:
                    bbox = [int(bbox_raw[0]), int(bbox_raw[1]), int(bbox_raw[2]), int(bbox_raw[3])]
                except (TypeError, ValueError):
                    bbox = []

            crop_b64 = None
            if orig_frame is not None and len(bbox) == 4:
                frame_h, frame_w = orig_frame.shape[:2]
                x1 = max(0, min(frame_w - 1, bbox[0]))
                y1 = max(0, min(frame_h - 1, bbox[1]))
                x2 = max(0, min(frame_w, bbox[2]))
                y2 = max(0, min(frame_h, bbox[3]))

                if x2 > x1 and y2 > y1:
                    crop = orig_frame[y1:y2, x1:x2]
                    if crop.size > 0:
                        ok, encoded = cv2.imencode(
                            ".jpg",
                            crop,
                            [int(cv2.IMWRITE_JPEG_QUALITY), 75],
                        )
                        if ok:
                            crop_b64 = base64.b64encode(encoded.tobytes()).decode("ascii")

            parking_status = str(plate.get("parking_status") or "LEGAL").strip().upper()
            if parking_status != "ILLEGAL":
                parking_status = "LEGAL"

            normalized.append(
                {
                    "track_id": plate.get("track_id"),
                    "plate_text": str(plate.get("plate_text") or "").strip().upper(),
                    "parking_status": parking_status,
                    "latitude": _safe_float(plate.get("latitude")),
                    "longitude": _safe_float(plate.get("longitude")),
                    "confidence": _safe_float(plate.get("confidence")),
                    "bbox": bbox,
                    "crop_b64": crop_b64,
                    "updated_at_utc": now,
                }
            )

        with self._lock:
            self._state["plates"] = normalized
            self._state["updated_at_utc"] = now

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)


ops_state_store = OpsStateStore()

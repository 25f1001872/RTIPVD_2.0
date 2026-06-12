"""Frame and GPS transport packet schema."""

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import cv2
import numpy as np

from src.database.models import GPSFix


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def parse_iso_ts(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class FrameTelemetryPacket:
    """Payload carried from Raspberry Pi sender to laptop server."""

    sequence_id: int
    frame_timestamp_utc: str
    gps: Dict[str, Any]
    frame_jpeg_base64: str

    @classmethod
    def from_frame(cls, sequence_id: int, frame: np.ndarray, gps_fix: GPSFix, jpeg_quality: int = 75) -> "FrameTelemetryPacket":
        quality = int(max(20, min(jpeg_quality, 95)))
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            raise RuntimeError("JPEG encoding failed")

        frame_b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
        return cls(
            sequence_id=sequence_id,
            frame_timestamp_utc=utc_iso_now(),
            gps=gps_fix.to_dict(),
            frame_jpeg_base64=frame_b64,
        )

    def to_json(self) -> Dict[str, Any]:
        return {
            "sequence_id": self.sequence_id,
            "frame_timestamp_utc": self.frame_timestamp_utc,
            "gps": self.gps,
            "frame_jpeg_base64": self.frame_jpeg_base64,
        }

    @classmethod
    def from_json(cls, payload: Dict[str, Any]) -> "FrameTelemetryPacket":
        return cls(
            sequence_id=int(payload.get("sequence_id", 0)),
            frame_timestamp_utc=str(payload.get("frame_timestamp_utc", "")),
            gps=dict(payload.get("gps", {})),
            frame_jpeg_base64=str(payload.get("frame_jpeg_base64", "")),
        )

    def decode_frame(self) -> Optional[np.ndarray]:
        if not self.frame_jpeg_base64:
            return None
        try:
            raw = base64.b64decode(self.frame_jpeg_base64.encode("ascii"), validate=True)
        except Exception:
            return None

        arr = np.frombuffer(raw, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame

"""GPS-to-video timestamp synchronization buffer."""

from datetime import datetime, timezone
from typing import List, Optional

from src.database.models import GPSFix
from src.streaming.packet import parse_iso_ts


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _convert_coordinate(coord: float) -> Optional[float]:
    """Convert raw GPS coordinate (ddmm.mmmm) using specific formula."""
    if coord is None:
        return None

    try:
        coord = float(coord)
    except (TypeError, ValueError):
        return None

    # First step divide the receiving coordinate by 100
    divided = coord / 100.0

    sign = -1.0 if divided < 0 else 1.0
    divided = abs(divided)

    # Got (x.y) two part one fractional (after decimal (y)) and one before decimal (x)
    x = int(divided)
    y = divided - x

    # Second step divide the fractional(y) again by 0.6
    y_converted = y / 0.6

    return sign * (x + y_converted)


def _is_valid_lat_lon(latitude: Optional[float], longitude: Optional[float]) -> bool:
    if latitude is None or longitude is None:
        return False
    return -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0


class GPSSyncBuffer:
    """Stores recent GPS fixes and resolves nearest fix for a frame timestamp."""

    def __init__(self, max_size: int = 512):
        self.max_size = max(16, max_size)
        self._items: List[GPSFix] = []

    def add_fix(self, fix: GPSFix) -> None:
        self._items.append(fix)
        if len(self._items) > self.max_size:
            self._items = self._items[-self.max_size :]

    def get_closest(self, frame_ts_utc: str, max_age_seconds: float = 2.0) -> Optional[GPSFix]:
        target = parse_iso_ts(frame_ts_utc)
        if target is None or not self._items:
            return None

        best_fix = None
        best_delta = None

        for fix in self._items:
            ts = fix.timestamp
            if ts.tzinfo is None:
                continue
            delta = abs((ts - target).total_seconds())
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_fix = fix

        if best_fix is None:
            return None

        if best_delta is not None and best_delta > max_age_seconds:
            return None

        return best_fix

    @staticmethod
    def parse_fix(payload: dict) -> GPSFix:
        ts = parse_iso_ts(str(payload.get("timestamp", "")))
        if ts is None:
            ts = datetime.now(timezone.utc)

        source = str(payload.get("source", "stream"))
        coord_format = str(
            payload.get("coord_format")
            or payload.get("gps_format")
            or payload.get("coordinate_format")
            or ""
        ).strip().lower()
        force_div100 = coord_format in {
            "ddmm_div100",
            "ddmm/100",
            "legacy_ddmm",
            "legacy_ddmm_div100",
        }

        latitude = _to_float(payload.get("latitude"))
        if latitude is None:
            latitude = _to_float(payload.get("lat"))
        if latitude is not None:
            latitude = _convert_coordinate(latitude)

        longitude = _to_float(payload.get("longitude"))
        if longitude is None:
            longitude = _to_float(payload.get("lon"))
        if longitude is not None:
            longitude = _convert_coordinate(longitude)

        if not _is_valid_lat_lon(latitude, longitude):
            latitude = None
            longitude = None

        has_coords = latitude is not None and longitude is not None
        if "fix" in payload:
            fix = bool(payload.get("fix", False)) and has_coords
        else:
            fix = has_coords

        return GPSFix(
            latitude=latitude,
            longitude=longitude,
            satellites=payload.get("satellites"),
            heading_deg=payload.get("heading_deg"),
            speed_mps=payload.get("speed_mps"),
            fix=fix,
            source=source,
            timestamp=ts,
        )

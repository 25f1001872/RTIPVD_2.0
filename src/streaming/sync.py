"""GPS-to-video timestamp synchronization buffer."""

from datetime import datetime, timezone
import math
import re
from typing import List, Optional, Tuple

from config.config import (
    STREAM_COORD_INPUT_FORMAT,
    STREAM_COORD_UTM_HEMISPHERE,
    STREAM_COORD_UTM_ZONE,
)
from src.database.models import GPSFix
from src.streaming.packet import parse_iso_ts


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


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value, default: bool = False) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_zone_number(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    zone = int(value)
    if 1 <= zone <= 60:
        return zone
    return None


def _parse_zone_token(raw) -> Tuple[Optional[int], Optional[str]]:
    if raw is None:
        return None, None

    text = str(raw).strip().upper().replace(" ", "")
    if not text:
        return None, None

    match = re.match(r"^(\d{1,2})([C-HJ-NP-X])?$", text)
    if not match:
        return None, None

    zone = _normalize_zone_number(_to_int(match.group(1)))
    if zone is None:
        return None, None

    letter = match.group(2)
    return zone, letter


def _is_valid_lat_lon(latitude: Optional[float], longitude: Optional[float]) -> bool:
    if latitude is None or longitude is None:
        return False
    return -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0


def _is_utm_easting(value: float) -> bool:
    return 100000.0 <= abs(value) <= 1000000.0


def _is_utm_northing(value: float) -> bool:
    return 10000.0 <= abs(value) <= 10000000.0


def _infer_utm_pair(first: float, second: float) -> Optional[Tuple[float, float]]:
    if _is_utm_easting(first) and _is_utm_northing(second):
        return first, second
    if _is_utm_easting(second) and _is_utm_northing(first):
        return second, first
    return None


def _parse_epsg_hint(raw) -> Tuple[Optional[int], Optional[bool]]:
    if raw is None:
        return None, None

    text = str(raw).upper().strip()
    match = re.search(r"(326|327)(\d{2})", text)
    if not match:
        return None, None

    prefix = match.group(1)
    zone = _normalize_zone_number(_to_int(match.group(2)))
    if zone is None:
        return None, None

    return zone, prefix == "327"


def _parse_utm_zone(payload: dict) -> Tuple[Optional[int], Optional[str], Optional[bool]]:
    zone_number = _normalize_zone_number(_to_int(payload.get("zone_number")))
    if zone_number is None:
        zone_number = _normalize_zone_number(_to_int(payload.get("utm_zone_number")))

    zone_letter = None
    zone_letter_raw = payload.get("zone_letter")
    if zone_letter_raw is None:
        zone_letter_raw = payload.get("utm_zone_letter")
    if zone_letter_raw is not None:
        letter = str(zone_letter_raw).strip().upper()[:1]
        if letter and letter.isalpha():
            zone_letter = letter

    if zone_number is None:
        for key in ("utm_zone", "zone", "grid_zone"):
            parsed_zone, parsed_letter = _parse_zone_token(payload.get(key))
            if parsed_zone is not None:
                zone_number = parsed_zone
                if zone_letter is None:
                    zone_letter = parsed_letter
                break

    epsg_zone, epsg_southern = _parse_epsg_hint(
        payload.get("epsg") or payload.get("epsg_code") or payload.get("crs")
    )
    if zone_number is None and epsg_zone is not None:
        zone_number = epsg_zone

    return zone_number, zone_letter, epsg_southern


def _resolve_is_southern(
    payload: dict,
    zone_letter: Optional[str],
    epsg_southern_hint: Optional[bool],
) -> bool:
    for key in ("is_southern", "southern_hemisphere", "utm_southern"):
        if key in payload:
            return bool(payload.get(key))

    hemisphere_raw = payload.get("hemisphere")
    if hemisphere_raw is None:
        hemisphere_raw = payload.get("utm_hemisphere")
    if hemisphere_raw is not None:
        hemisphere = str(hemisphere_raw).strip().upper()
        if hemisphere.startswith("S"):
            return True
        if hemisphere.startswith("N"):
            return False

    if zone_letter is not None:
        return zone_letter < "N"

    if epsg_southern_hint is not None:
        return epsg_southern_hint

    return str(STREAM_COORD_UTM_HEMISPHERE).strip().upper().startswith("S")


def _utm_to_lat_lon(
    easting: float,
    northing: float,
    zone_number: int,
    is_southern: bool,
) -> Optional[Tuple[float, float]]:
    if not _is_utm_easting(easting) or not _is_utm_northing(northing):
        return None

    # WGS84 UTM conversion (EPSG:326xx/327xx).
    a = 6378137.0
    ecc_squared = 0.0066943799901413165
    k0 = 0.9996
    ecc_prime_squared = ecc_squared / (1.0 - ecc_squared)

    x = easting - 500000.0
    y = northing
    if is_southern:
        y -= 10000000.0

    long_origin = (zone_number - 1) * 6 - 180 + 3

    m = y / k0
    mu = m / (
        a
        * (
            1
            - ecc_squared / 4
            - 3 * ecc_squared * ecc_squared / 64
            - 5 * ecc_squared * ecc_squared * ecc_squared / 256
        )
    )

    e1 = (1 - math.sqrt(1 - ecc_squared)) / (1 + math.sqrt(1 - ecc_squared))

    phi1_rad = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )

    sin_phi1 = math.sin(phi1_rad)
    cos_phi1 = math.cos(phi1_rad)
    tan_phi1 = math.tan(phi1_rad)

    n1 = a / math.sqrt(1 - ecc_squared * sin_phi1 * sin_phi1)
    t1 = tan_phi1 * tan_phi1
    c1 = ecc_prime_squared * cos_phi1 * cos_phi1
    r1 = a * (1 - ecc_squared) / pow(1 - ecc_squared * sin_phi1 * sin_phi1, 1.5)
    d = x / (n1 * k0)

    lat_rad = phi1_rad - (n1 * tan_phi1 / r1) * (
        d * d / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * ecc_prime_squared) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * ecc_prime_squared - 3 * c1 * c1)
        * d**6
        / 720
    )

    lon_rad = (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * ecc_prime_squared + 24 * t1 * t1)
        * d**5
        / 120
    ) / cos_phi1

    latitude = math.degrees(lat_rad)
    longitude = long_origin + math.degrees(lon_rad)

    if not _is_valid_lat_lon(latitude, longitude):
        return None

    return latitude, longitude


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

        easting = _to_float(payload.get("easting"))
        if easting is None:
            easting = _to_float(payload.get("utm_easting"))
        if easting is None:
            easting = _to_float(payload.get("x"))

        northing = _to_float(payload.get("northing"))
        if northing is None:
            northing = _to_float(payload.get("utm_northing"))
        if northing is None:
            northing = _to_float(payload.get("y"))

        inferred_utm = False
        if (easting is None or northing is None) and latitude is not None and longitude is not None:
            inferred_pair = _infer_utm_pair(latitude, longitude)
            if inferred_pair is not None:
                easting, northing = inferred_pair
                inferred_utm = True

        coord_mode = str(STREAM_COORD_INPUT_FORMAT).strip().lower()
        should_use_utm = easting is not None and northing is not None
        if coord_mode == "latlon":
            should_use_utm = False
        elif coord_mode == "utm":
            should_use_utm = easting is not None and northing is not None

        if should_use_utm:
            zone_number, zone_letter, epsg_southern_hint = _parse_utm_zone(payload)
            if zone_number is None:
                zone_number = _normalize_zone_number(STREAM_COORD_UTM_ZONE)

            if zone_number is not None:
                is_southern = _resolve_is_southern(payload, zone_letter, epsg_southern_hint)
                converted = _utm_to_lat_lon(
                    easting=easting,
                    northing=northing,
                    zone_number=zone_number,
                    is_southern=is_southern,
                )
                if converted is not None:
                    latitude, longitude = converted
                    if inferred_utm:
                        source = f"{source}:utm"

        if not _is_valid_lat_lon(latitude, longitude):
            latitude = None
            longitude = None

        satellites = _to_int(payload.get("satellites"))
        heading_deg = _to_float(payload.get("heading_deg"))
        speed_mps = _to_float(payload.get("speed_mps"))

        has_coords = latitude is not None and longitude is not None
        if "fix" in payload:
            fix = _to_bool(payload.get("fix"), default=False) and has_coords
        else:
            # If an upstream sender omits the fix flag but provides valid coordinates,
            # treat it as usable for geospatial projection.
            fix = has_coords

        return GPSFix(
            latitude=latitude,
            longitude=longitude,
            satellites=satellites,
            heading_deg=heading_deg,
            speed_mps=speed_mps,
            fix=fix,
            source=source,
            timestamp=ts,
        )

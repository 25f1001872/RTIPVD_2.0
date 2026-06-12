"""
GeoJSON-based no-parking zone checker for RTIPVD.

Loads Polygon/MultiPolygon features from a GeoJSON file and checks
whether a vehicle's estimated latitude/longitude falls inside any zone.
"""

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config.config import (
    ILLEGAL_PARKING_GEOJSON_ENABLED,
    ILLEGAL_PARKING_GEOJSON_PATH,
)


Coord = Tuple[float, float]  # (lon, lat)


@dataclass
class ZoneMatch:
    """Metadata for a matched no-parking zone."""

    zone_id: str
    zone_name: str
    properties: Dict[str, Any]


@dataclass
class _PolygonShape:
    """One polygon shape (outer ring + optional holes)."""

    outer: List[Coord]
    holes: List[List[Coord]]
    bbox: Tuple[float, float, float, float]  # min_lon, min_lat, max_lon, max_lat


@dataclass
class _LineShape:
    """One line shape (MultiLineString or LineString)."""

    points: List[Coord]
    bbox: Tuple[float, float, float, float]
    buffer_meters: float = 8.0  # Configurable zone size around the line


class NoParkingZoneChecker:
    """Checks whether a point falls inside configured no-parking zones."""

    def __init__(
        self,
        enabled: bool = ILLEGAL_PARKING_GEOJSON_ENABLED,
        geojson_path: str = ILLEGAL_PARKING_GEOJSON_PATH,
    ):
        self.enabled = bool(enabled)
        self.geojson_path = self._resolve_geojson_path(Path(geojson_path))
        self._zones: List[Dict[str, Any]] = []

        if self.enabled:
            self._load_geojson()

    @staticmethod
    def _resolve_geojson_path(path: Path) -> Path:
        """
        Resolve GeoJSON path robustly across case-sensitive/case-insensitive filesystems.

        If the exact file path does not exist, this attempts a case-insensitive match in
        the same directory (for example: no_parking_zones.geojson vs No_Parking_Zones.geojson).
        """
        if path.exists():
            return path

        parent = path.parent
        if not parent.exists() or not parent.is_dir():
            return path

        target_name = path.name.lower()
        try:
            for candidate in parent.iterdir():
                if candidate.is_file() and candidate.name.lower() == target_name:
                    return candidate
        except OSError:
            return path

        return path

    @property
    def zone_count(self) -> int:
        """Number of loaded zone features."""
        return len(self._zones)

    @property
    def is_ready(self) -> bool:
        """True when enabled and at least one zone polygon is loaded."""
        return self.enabled and self.zone_count > 0

    def find_zone(
        self, latitude: Optional[float], longitude: Optional[float]
    ) -> Optional[ZoneMatch]:
        """Return the first matching zone for a point, else None."""
        if not self.enabled or latitude is None or longitude is None:
            return None

        if not self._zones:
            return None

        lon = float(longitude)
        lat = float(latitude)

        for zone in self._zones:
            for poly in zone.get("polygons", []):
                if not self._in_bbox(lon, lat, poly.bbox):
                    continue
                if self._point_in_polygon(lon, lat, poly):
                    return ZoneMatch(
                        zone_id=zone["zone_id"],
                        zone_name=zone["zone_name"],
                        properties=dict(zone["properties"]),
                    )

            for line in zone.get("lines", []):
                if not self._in_bbox(lon, lat, line.bbox):
                    continue
                if self._point_near_line(lon, lat, line):
                    return ZoneMatch(
                        zone_id=zone["zone_id"],
                        zone_name=zone["zone_name"],
                        properties=dict(zone["properties"]),
                    )

        return None

    def contains(self, latitude: Optional[float], longitude: Optional[float]) -> bool:
        """Boolean wrapper around find_zone()."""
        return self.find_zone(latitude, longitude) is not None

    def _load_geojson(self) -> None:
        """Load zones from GeoJSON file."""
        if not self.geojson_path.exists():
            print(
                f"[NoParkingZoneChecker] WARNING: GeoJSON not found: {self.geojson_path}. "
                "Illegal parking geofence checks will not match any zone."
            )
            return

        try:
            data = json.loads(self.geojson_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[NoParkingZoneChecker] WARNING: Failed to read GeoJSON: {exc}")
            return

        features = self._extract_features(data)
        loaded = []

        for idx, feature in enumerate(features, start=1):
            geometry = feature.get("geometry") or {}
            props = dict(feature.get("properties") or {})

            # Use buffer property if provided in the GeoJSON (default to 8m)
            buffer_m = float(props.get("buffer_meters", 8.0))

            parsed_geoms = self._parse_geometry(geometry, buffer_m)
            if not parsed_geoms.get("polygons") and not parsed_geoms.get("lines"):
                continue

            zone_id = str(
                props.get("zone_id")
                or props.get("id")
                or feature.get("id")
                or f"zone_{idx}"
            )
            zone_name = str(props.get("name") or props.get("zone_name") or zone_id)

            loaded.append(
                {
                    "zone_id": zone_id,
                    "zone_name": zone_name,
                    "properties": props,
                    "polygons": parsed_geoms["polygons"],
                    "lines": parsed_geoms["lines"],
                }
            )

        self._zones = loaded
        print(
            f"[NoParkingZoneChecker] Loaded {self.zone_count} zone(s) from {self.geojson_path}"
        )

    def _extract_features(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Normalize GeoJSON payload into a feature list."""
        geo_type = str(payload.get("type", "")).strip()

        if geo_type == "FeatureCollection":
            features = payload.get("features")
            return features if isinstance(features, list) else []

        if geo_type == "Feature":
            return [payload]

        # Bare geometry fallback.
        if "coordinates" in payload and "type" in payload:
            return [{"type": "Feature", "properties": {}, "geometry": payload}]

        return []

    def _parse_geometry(
        self, geometry: Dict[str, Any], buffer_m: float
    ) -> Dict[str, List]:
        """Parse geometry into polygons and lines."""
        geo_type = str(geometry.get("type", "")).strip()
        coords = geometry.get("coordinates")
        result = {"polygons": [], "lines": []}

        if not isinstance(coords, list):
            return result

        if geo_type == "Polygon":
            polygon = self._parse_polygon_coords(coords)
            if polygon is not None:
                result["polygons"].append(polygon)

        elif geo_type == "MultiPolygon":
            for item in coords:
                if not isinstance(item, list):
                    continue
                polygon = self._parse_polygon_coords(item)
                if polygon is not None:
                    result["polygons"].append(polygon)

        elif geo_type == "LineString":
            line = self._parse_line_coords(coords, buffer_m)
            if line is not None:
                result["lines"].append(line)

        elif geo_type == "MultiLineString":
            for item in coords:
                if not isinstance(item, list):
                    continue
                line = self._parse_line_coords(item, buffer_m)
                if line is not None:
                    result["lines"].append(line)

        return result

    def _parse_line_coords(
        self, coords: List[Any], buffer_m: float
    ) -> Optional[_LineShape]:
        points = self._normalize_ring(coords, close_ring=False)
        if len(points) < 2:
            return None
        lons = [p[0] for p in points]
        lats = [p[1] for p in points]

        # Add buffer degrees approx to bbox for fast reject
        # 1 degree approx 111km, so buffer_m / 111000 buffer
        b_deg = buffer_m / 111000.0
        bbox = (
            min(lons) - b_deg,
            min(lats) - b_deg,
            max(lons) + b_deg,
            max(lats) + b_deg,
        )
        return _LineShape(points=points, bbox=bbox, buffer_meters=buffer_m)

    def _parse_polygon_coords(
        self, polygon_coords: List[Any]
    ) -> Optional[_PolygonShape]:
        """Build a _PolygonShape from one Polygon coordinate list."""
        if not polygon_coords:
            return None

        outer = self._normalize_ring(polygon_coords[0])
        if len(outer) < 3:
            return None

        holes: List[List[Coord]] = []
        for hole_coords in polygon_coords[1:]:
            hole = self._normalize_ring(hole_coords)
            if len(hole) >= 3:
                holes.append(hole)

        lons = [pt[0] for pt in outer]
        lats = [pt[1] for pt in outer]
        bbox = (min(lons), min(lats), max(lons), max(lats))

        return _PolygonShape(outer=outer, holes=holes, bbox=bbox)

    def _normalize_ring(self, raw_ring: Any, close_ring: bool = True) -> List[Coord]:
        """Normalize one GeoJSON ring into a clean coordinate list."""
        if not isinstance(raw_ring, list):
            return []

        ring: List[Coord] = []
        for pair in raw_ring:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            try:
                lon = float(pair[0])
                lat = float(pair[1])
            except (TypeError, ValueError):
                continue
            ring.append((lon, lat))

        if close_ring and len(ring) >= 2 and ring[0] == ring[-1]:
            ring.pop()

        return ring

    def _in_bbox(
        self, lon: float, lat: float, bbox: Tuple[float, float, float, float]
    ) -> bool:
        """Fast bounding-box precheck before full polygon math."""
        min_lon, min_lat, max_lon, max_lat = bbox
        return (min_lon <= lon <= max_lon) and (min_lat <= lat <= max_lat)

    def _point_in_polygon(self, lon: float, lat: float, polygon: _PolygonShape) -> bool:
        """Point-in-polygon with hole exclusion."""
        if not self._point_in_ring(lon, lat, polygon.outer):
            return False

        for hole in polygon.holes:
            if self._point_in_ring(lon, lat, hole):
                return False

        return True

    def _point_in_ring(self, lon: float, lat: float, ring: List[Coord]) -> bool:
        """Ray-casting point-in-ring test (boundary-inclusive)."""
        inside = False
        n = len(ring)
        if n < 3:
            return False

        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]

            if self._point_on_segment(lon, lat, xj, yj, xi, yi):
                return True

            intersects = ((yi > lat) != (yj > lat)) and (
                lon < ((xj - xi) * (lat - yi) / ((yj - yi) + 1e-12) + xi)
            )
            if intersects:
                inside = not inside
            j = i

        return inside

    def _point_on_segment(
        self,
        px: float,
        py: float,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        epsilon: float = 1e-9,
    ) -> bool:
        """Check whether a point lies on a line segment."""
        cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
        if abs(cross) > epsilon:
            return False

        dot = (px - x1) * (px - x2) + (py - y1) * (py - y2)
        return dot <= epsilon

    def _distance_point_to_segment(
        self, px: float, py: float, x1: float, y1: float, x2: float, y2: float
    ) -> float:
        """Calculate minimum distance in meters between point and line segment."""
        # Simple equirectangular approximation
        R = 6371000.0  # Earth radius in meters

        # Convert to radians
        lat1, lon1 = math.radians(y1), math.radians(x1)
        lat2, lon2 = math.radians(y2), math.radians(x2)
        plat, plon = math.radians(py), math.radians(px)

        # Local equirectangular projection to meters from (plon, plat)
        # (0, 0) is the point of interest
        x1_m = (lon1 - plon) * math.cos(plat) * R
        y1_m = (lat1 - plat) * R

        x2_m = (lon2 - plon) * math.cos(plat) * R
        y2_m = (lat2 - plat) * R

        dx = x2_m - x1_m
        dy = y2_m - y1_m
        l2 = dx * dx + dy * dy

        if l2 == 0.0:
            return math.hypot(x1_m, y1_m)

        # Parameter of projection on segment
        t = -(x1_m * dx + y1_m * dy) / (l2 + 1e-12)
        t = max(0.0, min(1.0, t))

        proj_x = x1_m + t * dx
        proj_y = y1_m + t * dy

        return math.hypot(proj_x, proj_y)

    def _point_near_line(self, lon: float, lat: float, line: _LineShape) -> bool:
        """Check if point is within buffer distance of line."""
        for i in range(len(line.points) - 1):
            x1, y1 = line.points[i]
            x2, y2 = line.points[i + 1]
            dist = self._distance_point_to_segment(lon, lat, x1, y1, x2, y2)
            if dist <= line.buffer_meters:
                return True
        return False

    def __repr__(self) -> str:
        state = "enabled" if self.enabled else "disabled"
        return (
            f"NoParkingZoneChecker(state={state}, "
            f"zones={self.zone_count}, "
            f"path='{self.geojson_path}')"
        )

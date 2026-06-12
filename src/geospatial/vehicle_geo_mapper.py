import math
from dataclasses import dataclass
from typing import Optional, Tuple

EARTH_RADIUS_M = 6378137.0


@dataclass
class GeoEstimate:
    """Estimated world position for one detected vehicle."""
    latitude: float
    longitude: float
    distance_m: float
    bearing_deg: float
    confidence: float


class VehicleGeoMapper:
    """Projects image detections into geospatial estimates."""

    def __init__(
        self,
        horizontal_fov_deg: float = 78.0,
        assumed_vehicle_height_m: float = 1.5,
        min_distance_m: float = 2.0,
        max_distance_m: float = 120.0,
    ):
        self.horizontal_fov_deg = max(10.0, min(horizontal_fov_deg, 179.0))
        self.assumed_vehicle_height_m = max(0.5, assumed_vehicle_height_m)
        self.min_distance_m = max(0.5, min_distance_m)
        self.max_distance_m = max(self.min_distance_m, max_distance_m)

    @staticmethod
    def _normalize_heading(heading_deg: float) -> float:
        """Normalize heading to [0, 360)."""
        return heading_deg % 360.0

    @staticmethod
    def _destination_point(
        latitude: float,
        longitude: float,
        bearing_deg: float,
        distance_m: float,
    ) -> Tuple[float, float]:
        """Move from an origin point by bearing and distance on Earth sphere."""
        lat1 = math.radians(latitude)
        lon1 = math.radians(longitude)
        bearing = math.radians(bearing_deg)
        angular_distance = distance_m / EARTH_RADIUS_M

        lat2 = math.asin(
            math.sin(lat1) * math.cos(angular_distance)
            + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
        )

        lon2 = lon1 + math.atan2(
            math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
            math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
        )

        return math.degrees(lat2), math.degrees(lon2)

    def _estimate_distance(
        self,
        bbox_h_px: float,
        frame_h: int,
        frame_w: int,
    ) -> Optional[float]:
        """Estimate distance using pinhole-camera geometry from bbox height."""
        if bbox_h_px <= 0:
            return None

        h_fov = math.radians(self.horizontal_fov_deg)
        # Approximate focal length in pixels using horizontal FOV.
        focal_length_px = frame_w / (2.0 * math.tan(h_fov / 2.0))

        distance_m = (self.assumed_vehicle_height_m * focal_length_px) / float(bbox_h_px)
        distance_m = max(self.min_distance_m, min(distance_m, self.max_distance_m))
        return distance_m

    def estimate_from_bbox(
        self,
        camera_lat: float,
        camera_lon: float,
        camera_heading_deg: float,
        bbox_xyxy: Tuple[float, float, float, float],
        frame_shape: Tuple[int, int],
    ) -> Optional[GeoEstimate]:
        """
        Estimate geolocation for one detected box from WGS84 inputs.
        """

        frame_h, frame_w = frame_shape
        x1, y1, x2, y2 = bbox_xyxy

        bbox_h = max(1.0, y2 - y1)
        bbox_w = max(1.0, x2 - x1)
        cx = (x1 + x2) / 2.0

        distance_m = self._estimate_distance(bbox_h, frame_h, frame_w)
        if distance_m is None:
            return None

        # Horizontal image offset -> bearing offset using camera horizontal FOV.
        px_offset = cx - (frame_w / 2.0)
        norm_offset = px_offset / max(frame_w / 2.0, 1.0)
        bearing_offset = norm_offset * (self.horizontal_fov_deg / 2.0)

        absolute_bearing = self._normalize_heading(camera_heading_deg + bearing_offset)
        
        # 2. Project standard Lat/Lon to new destination
        est_lat, est_lon = self._destination_point(
            camera_lat,
            camera_lon,
            absolute_bearing,
            distance_m,
        )

        # Confidence heuristic from detection footprint size.
        area = bbox_h * bbox_w
        frame_area = max(frame_h * frame_w, 1)
        confidence = max(0.1, min(0.95, (area / frame_area) * 25.0))

        return GeoEstimate(
            latitude=est_lat,
            longitude=est_lon,
            distance_m=distance_m,
            bearing_deg=absolute_bearing,
            confidence=confidence,
        )
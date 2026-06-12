"""
RTIPVD database models.

Defines lightweight dataclasses used by the runtime pipeline,
SQLite manager, and backend API payloads.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utc_now() -> datetime:
	"""Return the current UTC timestamp."""
	return datetime.now(timezone.utc)


def to_utc_timestamp(value: datetime) -> str:
	"""Convert a datetime to a normalized UTC ISO string for storage."""
	if value.tzinfo is None:
		value = value.replace(tzinfo=timezone.utc)
	value = value.astimezone(timezone.utc)
	return value.isoformat(timespec="seconds")


def parse_timestamp(value: Optional[str]) -> Optional[datetime]:
	"""Parse a timestamp string from SQLite/API into a datetime object."""
	if not value:
		return None

	# Support both "...Z" and "+00:00" style UTC strings.
	normalized = value.replace("Z", "+00:00")
	try:
		parsed = datetime.fromisoformat(normalized)
	except ValueError:
		return None

	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=timezone.utc)
	return parsed.astimezone(timezone.utc)


@dataclass
class GPSFix:
		"""Current GPS fix information. Coordinates must be in WGS84 decimal degrees."""

		latitude: Optional[float] = None  # WGS84 decimal degrees (-90 to +90)
		longitude: Optional[float] = None  # WGS84 decimal degrees (-180 to +180)
	satellites: Optional[int] = None
	heading_deg: Optional[float] = None
	speed_mps: Optional[float] = None
	fix: bool = False
	source: str = "disabled"
	timestamp: datetime = field(default_factory=utc_now)

	def to_dict(self) -> Dict[str, Any]:
		"""Convert fix to a plain dictionary for logs and JSON payloads."""
		return {
			"latitude": self.latitude,
			"longitude": self.longitude,
			"satellites": self.satellites,
			"heading_deg": self.heading_deg,
			"speed_mps": self.speed_mps,
			"fix": self.fix,
			"source": self.source,
			"timestamp": to_utc_timestamp(self.timestamp),
		}


@dataclass
class ViolationRecord:
	"""Represents one violation row in local storage and API payloads."""

	license_plate: str
	first_seen: datetime
	last_seen: datetime
	duration_sec: float
	latitude: Optional[float] = None
	longitude: Optional[float] = None
	screenshot_path: Optional[str] = None
	video_source: Optional[str] = None
	confidence: Optional[float] = None

	def normalized_plate(self) -> str:
		"""Normalize license plate string before persistence/network sync."""
		return self.license_plate.strip().upper()

	def to_db_params(self) -> Dict[str, Any]:
		"""Convert record into SQLite-compatible named parameters."""
		return {
			"license_plate": self.normalized_plate(),
			"first_seen": to_utc_timestamp(self.first_seen),
			"last_seen": to_utc_timestamp(self.last_seen),
			"duration_sec": float(max(self.duration_sec, 0.0)),
			"latitude": self.latitude,
			"longitude": self.longitude,
			"screenshot_path": self.screenshot_path,
			"video_source": self.video_source,
			"confidence": self.confidence,
		}

	def to_api_payload(
		self,
		violation_id: Optional[int] = None,
		event_type: str = "updated",
	) -> Dict[str, Any]:
		"""Serialize record for backend ingestion endpoint."""
		payload = self.to_db_params()
		payload["event_type"] = event_type
		if violation_id is not None:
			payload["id"] = violation_id
		return payload

	@classmethod
	def from_db_row(cls, row: Dict[str, Any]) -> "ViolationRecord":
		"""Build a record from a sqlite3.Row/dict returned by DatabaseManager."""
		row = dict(row)
		first_seen = parse_timestamp(row.get("first_seen")) or utc_now()
		last_seen = parse_timestamp(row.get("last_seen")) or first_seen

		return cls(
			license_plate=row.get("license_plate", "").strip().upper(),
			first_seen=first_seen,
			last_seen=last_seen,
			duration_sec=float(row.get("duration_sec", 0.0) or 0.0),
			latitude=row.get("latitude"),
			longitude=row.get("longitude"),
			screenshot_path=row.get("screenshot_path"),
			video_source=row.get("video_source"),
			confidence=row.get("confidence"),
		)

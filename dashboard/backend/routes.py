"""REST API routes for the RTIPVD backend."""

from pathlib import Path

from flask import Blueprint, Flask, abort, current_app, jsonify, request, send_from_directory

from config.config import SCREENSHOTS_DIR
from src.database.models import ViolationRecord, parse_timestamp, utc_now


def _require_api_key() -> bool:
	"""Validate API key header when backend API key is configured."""
	expected = current_app.config.get("API_KEY", "")
	if not expected:
		return True

	provided = request.headers.get("X-API-Key", "")
	return provided == expected


def _to_float(value, default=None):
	if value is None:
		return default
	try:
		return float(value)
	except (TypeError, ValueError):
		return default


def _convert_raw_gps_to_decimal(raw_value: float, max_degrees: float):
	"""Convert raw GPS ddmm.mmmm format to decimal degrees using /100 then /0.6 formula.
	
	Args:
		raw_value: Raw GPS value (e.g., 2951.6747 for latitude, 7753.8555 for longitude)
		max_degrees: Max allowed degrees (90 for latitude, 180 for longitude)
	
	Returns:
		Converted decimal degrees or None if invalid.
	"""
	if raw_value is None:
		return None
	try:
		value = float(raw_value)
	except (TypeError, ValueError):
		return None

	# If already in decimal degrees range, return as-is
	if abs(value) <= max_degrees:
		return value

	# Otherwise, apply conversion: /100 then fractional /0.6
	value_div100 = value / 100.0
	sign = -1.0 if value_div100 < 0 else 1.0
	value_div100 = abs(value_div100)
	
	degrees = int(value_div100)
	fraction = value_div100 - degrees

	# Validate range [0, 0.60)
	if fraction < 0.0 or fraction >= 0.60:
		return None

	decimal = degrees + (fraction / 0.6)
	if decimal > max_degrees:
		return None

	return sign * decimal


def register_routes(app: Flask) -> None:
	"""Register all API endpoints on the provided Flask app."""
	api = Blueprint("api", __name__, url_prefix="/api")

	@api.get("/health")
	def health():
		db_manager = current_app.config["DB_MANAGER"]
		return jsonify(
			{
				"ok": True,
				"db_enabled": db_manager.enabled,
				"db_path": str(db_manager.db_path),
			}
		)

	@api.get("/violations")
	def list_violations():
		db_manager = current_app.config["DB_MANAGER"]

		try:
			limit = int(request.args.get("limit", 100))
		except ValueError:
			limit = 100
		limit = max(1, min(limit, 1000))

		records = db_manager.list_recent(limit=limit)
		return jsonify({"count": len(records), "items": records})

	@api.get("/screenshots/<path:filename>")
	def get_screenshot(filename: str):
		base_dir = Path(SCREENSHOTS_DIR).resolve()
		safe_name = Path(filename).name
		candidate = (base_dir / safe_name).resolve()

		try:
			candidate.relative_to(base_dir)
		except ValueError:
			abort(404)

		if not candidate.is_file():
			abort(404)

		return send_from_directory(str(base_dir), safe_name)

	@api.post("/violations")
	def upsert_violation():
		if not _require_api_key():
			return jsonify({"ok": False, "error": "Unauthorized"}), 401

		payload = request.get_json(silent=True) or {}
		plate = str(payload.get("license_plate", "")).strip().upper()
		if not plate:
			return jsonify({"ok": False, "error": "license_plate is required"}), 400

		first_seen = parse_timestamp(payload.get("first_seen")) or utc_now()
		last_seen = parse_timestamp(payload.get("last_seen")) or first_seen
		if last_seen < first_seen:
			last_seen = first_seen

		duration = _to_float(payload.get("duration_sec"), None)
		if duration is None:
			duration = max((last_seen - first_seen).total_seconds(), 0.0)

		# Ensure coordinates are in WGS84 decimal degrees (convert raw ddmm.mmmm if needed)
		latitude = _to_float(payload.get("latitude"), None)
		if latitude is not None and abs(latitude) > 90:
			latitude = _convert_raw_gps_to_decimal(latitude, max_degrees=90.0)

		longitude = _to_float(payload.get("longitude"), None)
		if longitude is not None and abs(longitude) > 180:
			longitude = _convert_raw_gps_to_decimal(longitude, max_degrees=180.0)

		record = ViolationRecord(
			license_plate=plate,
			first_seen=first_seen,
			last_seen=last_seen,
			duration_sec=duration,
			latitude=latitude,
			longitude=longitude,
			screenshot_path=payload.get("screenshot_path"),
			video_source=payload.get("video_source"),
			confidence=_to_float(payload.get("confidence"), None),
			parking_status=str(payload.get("parking_status", "LEGAL") or "LEGAL"),
			zone_id=payload.get("zone_id"),
			zone_name=payload.get("zone_name"),
		)

		db_manager = current_app.config["DB_MANAGER"]
		violation_id, inserted = db_manager.upsert_violation(record)

		status_code = 201 if inserted else 200
		return (
			jsonify(
				{
					"ok": True,
					"id": violation_id,
					"event_type": payload.get("event_type", "updated"),
					"inserted": inserted,
				}
			),
			status_code,
		)

	app.register_blueprint(api)

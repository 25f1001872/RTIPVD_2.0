"""
RTIPVD GPS tagger.

Reads coordinates from a serial NMEA source (ESP32 + NEO-6M)
or from configurable mock coordinates for laptop testing.
"""

import time
from datetime import timezone
from typing import Optional

from config.config import (
	GPS_BAUD_RATE,
	GPS_ENABLED,
	GPS_MOCK_LAT,
	GPS_MOCK_LON,
	GPS_READ_TIMEOUT_MS,
	GPS_SERIAL_PORT,
	GPS_SOURCE,
)
from src.database.models import GPSFix, utc_now

try:
	import serial
except ImportError:  # pragma: no cover - handled safely at runtime
	serial = None


def _nmea_to_decimal(raw_value: str, direction: str) -> Optional[float]:
	"""Convert NMEA coordinate format (ddmm.mmmm / dddmm.mmmm) to decimal."""
	if not raw_value or not direction:
		return None

	if direction not in {"N", "S", "E", "W"}:
		return None

	deg_len = 2 if direction in {"N", "S"} else 3
	if len(raw_value) <= deg_len:
		return None

	try:
		degrees = float(raw_value[:deg_len])
		minutes = float(raw_value[deg_len:])
	except ValueError:
		return None

	decimal = degrees + (minutes / 60.0)
	if direction in {"S", "W"}:
		decimal *= -1.0
	return decimal


def _parse_nmea_sentence(sentence: str) -> Optional[GPSFix]:
	"""Parse GPRMC/GNRMC/GPGGA/GNGGA NMEA sentences."""
	if not sentence.startswith("$"):
		return None

	parts = sentence.split(",")
	if len(parts) < 7:
		return None

	sentence_type = parts[0]
	now = utc_now()

	# Recommended Minimum Specific GNSS Data
	if sentence_type in {"$GPRMC", "$GNRMC"}:
		# Format: $GPRMC,time,status,lat,N,lon,E,...
		status = parts[2]
		if status != "A":
			return GPSFix(fix=False, source="serial", timestamp=now)

		latitude = _nmea_to_decimal(parts[3], parts[4])
		longitude = _nmea_to_decimal(parts[5], parts[6])
		if latitude is None or longitude is None:
			return None

		heading_deg = None
		speed_mps = None
		try:
			if len(parts) > 8 and parts[8]:
				heading_deg = float(parts[8])
		except ValueError:
			heading_deg = None

		# RMC speed is in knots.
		try:
			if len(parts) > 7 and parts[7]:
				speed_mps = float(parts[7]) * 0.514444
		except ValueError:
			speed_mps = None

		return GPSFix(
			latitude=latitude,
			longitude=longitude,
			satellites=None,
			heading_deg=heading_deg,
			speed_mps=speed_mps,
			fix=True,
			source="serial",
			timestamp=now,
		)

	# Global Positioning System Fix Data
	if sentence_type in {"$GPGGA", "$GNGGA"}:
		# Format: $GPGGA,time,lat,N,lon,E,fix_quality,num_sat,...
		fix_quality = parts[6]
		if not fix_quality or fix_quality == "0":
			return GPSFix(fix=False, source="serial", timestamp=now)

		latitude = _nmea_to_decimal(parts[2], parts[3])
		longitude = _nmea_to_decimal(parts[4], parts[5])
		satellites = None
		try:
			satellites = int(parts[7]) if parts[7] else None
		except ValueError:
			satellites = None

		if latitude is None or longitude is None:
			return None

		return GPSFix(
			latitude=latitude,
			longitude=longitude,
			satellites=satellites,
			fix=True,
			source="serial",
			timestamp=now,
		)

	return None


class GPSTagger:
	"""Provides latest GPS fix for evidence tagging."""

	def __init__(self):
		self.enabled = GPS_ENABLED
		self.source = GPS_SOURCE.strip().lower()
		self.serial_port = GPS_SERIAL_PORT
		self.baud_rate = GPS_BAUD_RATE
		self.read_timeout_ms = GPS_READ_TIMEOUT_MS
		self.mock_lat = GPS_MOCK_LAT
		self.mock_lon = GPS_MOCK_LON

		self._serial = None
		self._last_fix = GPSFix(fix=False, source="disabled", timestamp=utc_now())

		if self.enabled and self.source == "serial":
			self._open_serial()

	def _open_serial(self) -> None:
		"""Open serial device for continuous NMEA reads."""
		if serial is None:
			print("[GPSTagger] WARNING: pyserial not installed. Falling back to mock GPS source.")
			self.source = "mock"
			self.enabled = True
			return

		try:
			self._serial = serial.Serial(
				self.serial_port,
				self.baud_rate,
				timeout=0.1,
			)
			print(f"[GPSTagger] Listening on {self.serial_port} @ {self.baud_rate} baud")
		except Exception as exc:
			print(f"[GPSTagger] WARNING: Could not open GPS serial port: {exc}")
			print("[GPSTagger] INFO: Falling back to mock GPS source.")
			self.source = "mock"
			self.enabled = True

	@property
	def is_ready(self) -> bool:
		"""Return True if GPS is enabled and has a usable source."""
		if not self.enabled:
			return False
		if self.source == "mock":
			return True
		if self.source == "serial":
			return self._serial is not None
		return False

	def get_latest(self) -> GPSFix:
		"""Get the latest known fix from serial or mock source."""
		if not self.enabled:
			self._last_fix = GPSFix(fix=False, source="disabled", timestamp=utc_now())
			return self._last_fix

		if self.source == "mock":
			self._last_fix = GPSFix(
				latitude=self.mock_lat,
				longitude=self.mock_lon,
				satellites=10,
				fix=True,
				source="mock",
				timestamp=utc_now(),
			)
			return self._last_fix

		if self.source != "serial" or self._serial is None:
			self._last_fix = GPSFix(fix=False, source="unavailable", timestamp=utc_now())
			return self._last_fix

		deadline = time.monotonic() + (self.read_timeout_ms / 1000.0)
		while time.monotonic() < deadline:
			try:
				line = self._serial.readline().decode("utf-8", errors="ignore").strip()
			except Exception:
				break

			if not line:
				continue

			parsed = _parse_nmea_sentence(line)
			if parsed is None:
				continue

			if parsed.fix:
				self._last_fix = parsed
				return parsed

		# Keep last valid fix if no new sentence arrives in this cycle.
		if self._last_fix.timestamp.tzinfo is None:
			self._last_fix.timestamp = self._last_fix.timestamp.replace(tzinfo=timezone.utc)
		return self._last_fix

	def close(self) -> None:
		"""Close serial handle if opened."""
		if self._serial is not None:
			self._serial.close()
			self._serial = None

	def __repr__(self) -> str:
		state = "enabled" if self.enabled else "disabled"
		return f"GPSTagger(state={state}, source='{self.source}')"

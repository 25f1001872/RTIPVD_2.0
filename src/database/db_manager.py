"""
RTIPVD database manager.

Provides local SQLite persistence for violation records so that
the detection pipeline can run reliably on both laptop and
Raspberry Pi deployments.
"""

import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from config.config import DB_ENABLED, DB_MERGE_WINDOW_SECONDS, DB_PATH, PROJECT_ROOT
from src.database.models import ViolationRecord, parse_timestamp


class DatabaseManager:
	"""Handles creation, upsert, and query operations for violation records."""

	def __init__(
		self,
		db_path: str = DB_PATH,
		enabled: bool = DB_ENABLED,
		merge_window_seconds: float = DB_MERGE_WINDOW_SECONDS,
	):
		self.enabled = enabled
		self.db_path = Path(db_path)
		self.merge_window_seconds = float(max(merge_window_seconds, 0.0))
		self.schema_path = PROJECT_ROOT / "src" / "database" / "migrations" / "init_schema.sql"

		self._conn: Optional[sqlite3.Connection] = None
		self._lock = Lock()

		if self.enabled:
			self._connect()
			self._ensure_schema()

	def _connect(self) -> None:
		"""Open sqlite connection and create parent directory if required."""
		self.db_path.parent.mkdir(parents=True, exist_ok=True)
		self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
		self._conn.row_factory = sqlite3.Row

	def _ensure_schema(self) -> None:
		"""Initialize database tables and safely migrate older schemas."""
		if self._conn is None:
			return

		# Ensure the core table exists even if migration script is missing.
		self._ensure_table_exists()

		# Upgrade legacy DBs first so schema/index statements can run safely.
		self._ensure_columns()

		# Apply migration script last (idempotent CREATE IF NOT EXISTS statements).
		if self.schema_path.exists():
			script = self.schema_path.read_text(encoding="utf-8")
			with self._lock:
				self._conn.executescript(script)
				self._conn.commit()

	def _ensure_table_exists(self) -> None:
		"""Create base violations table when DB is empty or migration script is unavailable."""
		if self._conn is None:
			return

		fallback = """
		CREATE TABLE IF NOT EXISTS violations (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			license_plate TEXT NOT NULL,
			first_seen DATETIME NOT NULL,
			last_seen DATETIME NOT NULL,
			duration_sec REAL NOT NULL,
			latitude REAL,
			longitude REAL,
			screenshot_path TEXT,
			video_source TEXT,
			confidence REAL,
			parking_status TEXT NOT NULL DEFAULT 'LEGAL',
			zone_id TEXT,
			zone_name TEXT,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			UNIQUE(license_plate, first_seen)
		);
		"""

		with self._lock:
			assert self._conn is not None
			self._conn.executescript(fallback)
			self._conn.commit()

	def _ensure_columns(self) -> None:
		"""Ensure new columns exist for databases created with older schema."""
		if self._conn is None:
			return

		required_columns = {
			"parking_status": "TEXT NOT NULL DEFAULT 'LEGAL'",
			"zone_id": "TEXT",
			"zone_name": "TEXT",
		}

		with self._lock:
			assert self._conn is not None
			cursor = self._conn.cursor()
			cursor.execute("PRAGMA table_info(violations)")
			existing = {str(row[1]) for row in cursor.fetchall()}

			for column_name, column_def in required_columns.items():
				if column_name in existing:
					continue
				cursor.execute(
					f"ALTER TABLE violations ADD COLUMN {column_name} {column_def}"
				)

			cursor.execute(
				"CREATE INDEX IF NOT EXISTS idx_violations_status ON violations(parking_status)"
			)

			self._conn.commit()

	@property
	def is_ready(self) -> bool:
		"""Return True if the manager is enabled and connected."""
		return self.enabled and self._conn is not None

	def upsert_violation(self, record: ViolationRecord) -> Tuple[Optional[int], bool]:
		"""
		Insert or update a violation.

		Rows are merged by plate if the latest row for the same plate
		was updated recently (within merge_window_seconds).

		Returns:
			tuple: (row_id, inserted_new_row)
		"""
		if not self.is_ready:
			return None, False

		params = record.to_db_params()

		with self._lock:
			assert self._conn is not None
			cursor = self._conn.cursor()
			cursor.execute(
				"""
				SELECT id, first_seen, last_seen
				FROM violations
				WHERE license_plate = ?
				ORDER BY id DESC
				LIMIT 1
				""",
				(params["license_plate"],),
			)
			latest = cursor.fetchone()

			if latest is not None:
				latest_last = parse_timestamp(latest["last_seen"])
				latest_first = parse_timestamp(latest["first_seen"])
				current_last = parse_timestamp(params["last_seen"])

				if latest_last and current_last:
					gap = (current_last - latest_last).total_seconds()
					if gap <= self.merge_window_seconds:
						if latest_first is not None:
							params["duration_sec"] = max(
								(current_last - latest_first).total_seconds(),
								0.0,
							)

						cursor.execute(
							"""
							UPDATE violations
							SET
								last_seen = :last_seen,
								duration_sec = :duration_sec,
								latitude = COALESCE(:latitude, latitude),
								longitude = COALESCE(:longitude, longitude),
								screenshot_path = COALESCE(:screenshot_path, screenshot_path),
								video_source = COALESCE(:video_source, video_source),
								confidence = COALESCE(:confidence, confidence),
								parking_status = :parking_status,
								zone_id = :zone_id,
								zone_name = :zone_name
							WHERE id = :id
							""",
							{
								"id": latest["id"],
								**params,
							},
						)
						self._conn.commit()
						return int(latest["id"]), False

			cursor.execute(
				"""
				INSERT INTO violations (
					license_plate,
					first_seen,
					last_seen,
					duration_sec,
					latitude,
					longitude,
					screenshot_path,
					video_source,
					confidence,
					parking_status,
					zone_id,
					zone_name
				) VALUES (
					:license_plate,
					:first_seen,
					:last_seen,
					:duration_sec,
					:latitude,
					:longitude,
					:screenshot_path,
					:video_source,
					:confidence,
					:parking_status,
					:zone_id,
					:zone_name
				)
				""",
				params,
			)
			self._conn.commit()
			return int(cursor.lastrowid), True

	def get_violation(self, violation_id: int) -> Optional[Dict[str, Any]]:
		"""Fetch one violation row by ID."""
		if not self.is_ready:
			return None

		with self._lock:
			assert self._conn is not None
			cursor = self._conn.cursor()
			cursor.execute("SELECT * FROM violations WHERE id = ?", (violation_id,))
			row = cursor.fetchone()

		return dict(row) if row is not None else None

	def list_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
		"""List recent violations ordered by latest activity."""
		if not self.is_ready:
			return []

		safe_limit = max(1, int(limit))
		with self._lock:
			assert self._conn is not None
			cursor = self._conn.cursor()
			cursor.execute(
				"""
				SELECT *
				FROM violations
				ORDER BY last_seen DESC
				LIMIT ?
				""",
				(safe_limit,),
			)
			rows = cursor.fetchall()

		return [dict(row) for row in rows]

	def close(self) -> None:
		"""Close the sqlite connection."""
		with self._lock:
			if self._conn is not None:
				self._conn.close()
				self._conn = None

	def __repr__(self) -> str:
		state = "enabled" if self.enabled else "disabled"
		return f"DatabaseManager(state={state}, db_path='{self.db_path}')"

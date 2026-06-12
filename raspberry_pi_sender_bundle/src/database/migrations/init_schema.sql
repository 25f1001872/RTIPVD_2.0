-- ==============================================================
-- RTIPVD — Initial Database Schema [Phase 2]
-- File: src/database/migrations/init_schema.sql
-- ==============================================================
--
-- Run this to create the initial database tables.
-- SQLite compatible.
--
-- Usage:
--   sqlite3 output/db/rtipvd.db < src/database/migrations/init_schema.sql
-- ==============================================================

-- Violations table: one row per unique violation event
CREATE TABLE IF NOT EXISTS violations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    license_plate   TEXT NOT NULL,          -- e.g., "MH12AB1234"
    first_seen      DATETIME NOT NULL,      -- when vehicle was first detected as parked
    last_seen       DATETIME NOT NULL,      -- last frame where vehicle was parked
    duration_sec    REAL NOT NULL,           -- total parking duration in seconds
    latitude        REAL,                   -- GPS latitude (NULL if no GPS)
    longitude       REAL,                   -- GPS longitude (NULL if no GPS)
    screenshot_path TEXT,                   -- path to saved frame image
    video_source    TEXT,                   -- source video filename
    confidence      REAL,                   -- average YOLO detection confidence
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Index on plate for fast lookups
    UNIQUE(license_plate, first_seen)
);

-- Index for searching by location
CREATE INDEX IF NOT EXISTS idx_violations_location
    ON violations(latitude, longitude);

-- Index for searching by date
CREATE INDEX IF NOT EXISTS idx_violations_date
    ON violations(first_seen);

-- Index for searching by plate
CREATE INDEX IF NOT EXISTS idx_violations_plate
    ON violations(license_plate);
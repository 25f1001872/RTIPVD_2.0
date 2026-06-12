#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR:${PYTHONPATH:-}"

if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Run deploy/raspberry_pi/setup.sh first."
    exit 1
fi

source .venv/bin/activate

export RTIPVD_DEVICE="${RTIPVD_DEVICE:-cpu}"
export RTIPVD_MODEL_PATH="${RTIPVD_MODEL_PATH:-weights/best.pt}"
export RTIPVD_VIDEO_SOURCE="${RTIPVD_VIDEO_SOURCE:-data/videos/d1.mp4}"
export RTIPVD_OCR_USE_GPU="${RTIPVD_OCR_USE_GPU:-false}"
export RTIPVD_SHOW_DISPLAY="${RTIPVD_SHOW_DISPLAY:-true}"

export RTIPVD_DB_ENABLED="${RTIPVD_DB_ENABLED:-true}"
export RTIPVD_DB_PATH="${RTIPVD_DB_PATH:-output/db/rtipvd_pi.db}"

export RTIPVD_GPS_ENABLED="${RTIPVD_GPS_ENABLED:-true}"
export RTIPVD_GPS_SOURCE="${RTIPVD_GPS_SOURCE:-serial}"
export RTIPVD_GPS_SERIAL_PORT="${RTIPVD_GPS_SERIAL_PORT:-/dev/ttyUSB0}"
export RTIPVD_GPS_BAUD_RATE="${RTIPVD_GPS_BAUD_RATE:-9600}"

export RTIPVD_BACKEND_ENABLED="${RTIPVD_BACKEND_ENABLED:-false}"
export RTIPVD_BACKEND_URL="${RTIPVD_BACKEND_URL:-http://127.0.0.1:5000/api/violations}"
export RTIPVD_BACKEND_API_KEY="${RTIPVD_BACKEND_API_KEY:-}"

python main.py

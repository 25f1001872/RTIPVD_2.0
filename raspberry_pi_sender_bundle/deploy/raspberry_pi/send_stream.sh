#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Run deploy/raspberry_pi/setup.sh first."
    exit 1
fi

source .venv/bin/activate

export RTIPVD_GPS_ENABLED="${RTIPVD_GPS_ENABLED:-true}"
export RTIPVD_GPS_SOURCE="${RTIPVD_GPS_SOURCE:-serial}"
export RTIPVD_GPS_SERIAL_PORT="${RTIPVD_GPS_SERIAL_PORT:-/dev/ttyUSB0}"
export RTIPVD_GPS_BAUD_RATE="${RTIPVD_GPS_BAUD_RATE:-9600}"

VIDEO_SOURCE="${RTIPVD_VIDEO_SOURCE:-data/videos/d1.mp4}"
SERVER_URL="${RTIPVD_STREAM_SERVER_URL:-http://127.0.0.1:8088/ingest/frame}"
SEND_FPS="${RTIPVD_STREAM_SEND_FPS:-8}"
JPEG_QUALITY="${RTIPVD_STREAM_JPEG_QUALITY:-70}"

python deploy/raspberry_pi/send_video_and_gps.py \
  --video-source "$VIDEO_SOURCE" \
  --server-url "$SERVER_URL" \
  --target-fps "$SEND_FPS" \
  --jpeg-quality "$JPEG_QUALITY"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR:${PYTHONPATH:-}"

echo "[1/5] Updating apt packages..."
sudo apt update
sudo apt upgrade -y

echo "[2/5] Installing system dependencies..."
sudo apt install -y python3-venv python3-pip sqlite3 modemmanager network-manager

echo "[3/5] Creating virtual environment..."
if [ ! -d ".venv" ]; then
	python3 -m venv .venv
fi

source .venv/bin/activate

echo "[4/5] Installing Python dependencies..."
python -m pip install --upgrade pip
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
pip install -r dashboard/backend/requirements.txt

echo "[5/5] Creating required folders..."
mkdir -p data/videos
mkdir -p output/db

echo "Setup complete. Next: edit deploy/raspberry_pi/pi.env.example and run deploy/raspberry_pi/run_pi.sh"

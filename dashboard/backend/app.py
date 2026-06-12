"""
RTIPVD backend server entry point.

Exposes REST endpoints for violation ingestion and listing,
and serves a simple frontend dashboard for operators.
"""

import os
import sys
from pathlib import Path

import requests
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

# Ensure project root is importable when app is launched directly.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from config.config import DASHBOARD_DEBUG, DASHBOARD_HOST, DASHBOARD_PORT, STREAM_SERVER_PORT
from dashboard.backend.routes import register_routes
from src.database.db_manager import DatabaseManager


def create_app() -> Flask:
	"""Build and configure Flask app instance."""
	frontend_dir = PROJECT_ROOT / "dashboard" / "frontend"

	app = Flask(
		__name__,
		static_folder=str(frontend_dir),
		static_url_path="/dashboard/static",
	)
	CORS(app)

	db_manager = DatabaseManager()
	app.config["DB_MANAGER"] = db_manager
	app.config["API_KEY"] = os.getenv("RTIPVD_BACKEND_API_KEY", "")
	app.config["STREAM_SERVER_PORT"] = STREAM_SERVER_PORT

	register_routes(app)

	@app.get("/")
	def index():
		return send_from_directory(frontend_dir, "index.html")

	@app.get("/dashboard")
	def dashboard():
		return send_from_directory(frontend_dir, "index.html")

	@app.get("/operations")
	def operations():
		return send_from_directory(frontend_dir, "operations.html")

	@app.get("/api/ops/state")
	def ops_state_proxy():
		stream_server_port = int(app.config.get("STREAM_SERVER_PORT", STREAM_SERVER_PORT))
		upstream = f"http://127.0.0.1:{stream_server_port}/ops/state"
		try:
			resp = requests.get(upstream, timeout=2.0)
			resp.raise_for_status()
		except requests.RequestException as exc:
			return (
				jsonify(
					{
						"ok": False,
						"error": "stream_server_unavailable",
						"detail": str(exc),
					}
				),
				503,
			)

		try:
			payload = resp.json()
		except ValueError:
			return jsonify({"ok": False, "error": "invalid_upstream_json"}), 502

		if isinstance(payload, dict) and "ok" not in payload:
			payload["ok"] = True

		return jsonify(payload), resp.status_code

	return app


app = create_app()


if __name__ == "__main__":
	app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=DASHBOARD_DEBUG)

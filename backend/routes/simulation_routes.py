"""
routes/simulation_routes.py
------------------------------
POST /api/simulation
Body: {"zone_id": 1, "rainfall_mm_per_hour": 80, "duration_hours": 2, "drainage_blockage_percent": 40}

Returns the real current ("baseline") prediction alongside the simulated
what-if result, so the frontend can render a BEFORE/AFTER comparison.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify, request

from models import Zone
from services.simulation_service import run_simulation

simulation_bp = Blueprint("simulation", __name__)


@simulation_bp.route("/simulation", methods=["POST"])
def post_simulation():
    body = request.get_json(silent=True) or {}

    zone_id = body.get("zone_id")
    if zone_id is None:
        return jsonify({"data": None, "error": "Request body must include 'zone_id'."}), 400

    zone = Zone.query.get(zone_id)
    if zone is None:
        return jsonify({"data": None, "error": f"No zone with id {zone_id}"}), 404

    try:
        rainfall_mm_per_hour = float(body.get("rainfall_mm_per_hour", 0))
        duration_hours = float(body.get("duration_hours", 1))
        drainage_blockage_percent = float(body.get("drainage_blockage_percent", 0))
    except (TypeError, ValueError):
        return jsonify({
            "data": None,
            "error": "rainfall_mm_per_hour, duration_hours, and drainage_blockage_percent must be numbers.",
        }), 400

    if not (0 <= drainage_blockage_percent <= 100):
        return jsonify({"data": None, "error": "drainage_blockage_percent must be between 0 and 100."}), 400
    if rainfall_mm_per_hour < 0 or duration_hours <= 0:
        return jsonify({
            "data": None,
            "error": "rainfall_mm_per_hour must be >= 0 and duration_hours must be > 0.",
        }), 400

    result = run_simulation(zone, rainfall_mm_per_hour, duration_hours, drainage_blockage_percent)

    return jsonify({
        "data": result,
        "meta": {"source": "simulated", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200

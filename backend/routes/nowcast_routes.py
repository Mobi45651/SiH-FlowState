"""
routes/nowcast_routes.py
---------------------------
GET /api/nowcast                        -> 7-step forecast for every zone (READ ONLY)
GET /api/nowcast/<zone_id>               -> 7-step forecast for one zone (READ ONLY)
POST /api/nowcast/refresh                -> explicit DB refresh of predictions

Response shape matches the architecture doc's example:
{"zone_id": ..., "forecast": [{"time": "18:00", "rainfall_mm": ..., ...}]}

All the real work happens in services/nowcast_engine.py -- this file only
parses the request and shapes the JSON envelope.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify

from models import Zone
from services.nowcast_engine import build_all_zones_nowcast, get_cached_zone_nowcast, get_cached_all_zone_nowcasts
from services.rainfall_pipeline import run_pipeline_for_all_zones

nowcast_bp = Blueprint("nowcast", __name__)


@nowcast_bp.route("/nowcast", methods=["GET"])
def get_nowcast_all():
    # READ ONLY: never ingest weather or write flood_predictions here.
    results = get_cached_all_zone_nowcasts()
    return jsonify({
        "data": results,
        "meta": {"source": "computed", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200


@nowcast_bp.route("/nowcast/<int:zone_id>", methods=["GET"])
def get_nowcast_zone(zone_id):
    zone = Zone.query.get(zone_id)
    if zone is None:
        return jsonify({"data": None, "error": f"No zone with id {zone_id}"}), 404

    # READ ONLY: cached/stale data is handled by the engine without SQLite writes.
    result = get_cached_zone_nowcast(zone)
    return jsonify({
        "data": result,
        "meta": {"source": "computed", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200


@nowcast_bp.route("/nowcast/refresh", methods=["POST"])
def refresh_nowcast():
    """Explicit write operation. Run this from an admin job/manual refresh,
    never from a dashboard GET. This is the only HTTP nowcast endpoint that
    intentionally writes flood_predictions/rainfall data."""
    try:
        results = run_pipeline_for_all_zones()
        predictions = build_all_zones_nowcast(ensure_fresh_data=False)
        return jsonify({
            "data": predictions,
            "meta": {"source": "explicit_refresh", "weather_zones": len(results)},
        }), 200
    except Exception as exc:
        return jsonify({"data": None, "error": str(exc)}), 500

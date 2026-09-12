"""
routes/rainfall_routes.py
----------------------------
GET /api/rainfall?zone_id=<id>&from=<iso>&to=<iso>&source=observed|forecast|demo&limit=200

Reads directly from the rainfall_records table -- this endpoint never calls
Open-Meteo itself; use /api/weather?ingest=1 (or the run-pipeline CLI
command) to populate data first.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify, request

from models import Zone, RainfallRecord
from utils.time_utils import to_naive_utc

rainfall_bp = Blueprint("rainfall", __name__)


@rainfall_bp.route("/rainfall", methods=["GET"])
def get_rainfall():
    zone_id = request.args.get("zone_id", type=int)
    if zone_id is None:
        return jsonify({
            "data": None,
            "error": "zone_id query parameter is required, e.g. /api/rainfall?zone_id=1",
        }), 400

    zone = Zone.query.get(zone_id)
    if zone is None:
        return jsonify({"data": None, "error": f"No zone with id {zone_id}"}), 404

    query = RainfallRecord.query.filter_by(zone_id=zone_id)

    from_str = request.args.get("from")
    to_str = request.args.get("to")
    source = request.args.get("source")
    limit = request.args.get("limit", default=200, type=int)

    try:
        if from_str:
            query = query.filter(RainfallRecord.timestamp >= to_naive_utc(datetime.fromisoformat(from_str)))
        if to_str:
            query = query.filter(RainfallRecord.timestamp <= to_naive_utc(datetime.fromisoformat(to_str)))
    except ValueError:
        return jsonify({
            "data": None,
            "error": "from/to must be ISO 8601 datetimes, e.g. 2026-08-27T00:00:00",
        }), 400

    if source:
        if source not in ("observed", "forecast", "demo"):
            return jsonify({
                "data": None,
                "error": "source must be one of: observed, forecast, demo",
            }), 400
        query = query.filter(RainfallRecord.source == source)

    records = query.order_by(RainfallRecord.timestamp.asc()).limit(min(limit, 1000)).all()

    return jsonify({
        "data": {
            "zone": zone.to_dict(),
            "records": [r.to_dict() for r in records],
            "count": len(records),
        },
        "meta": {
            "source": "database",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }), 200

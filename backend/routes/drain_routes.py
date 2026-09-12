"""
routes/drain_routes.py
--------------------------
GET /api/drains                          -> every drain + its latest reading
GET /api/drains/<id>                     -> one drain, latest reading + recent history
POST /api/drains/<id>/simulate-blockage  -> body {"blockage_percent": 40} for the
                                             SIH demo walkthrough (NORMAL -> 10% ->
                                             30% -> 60%, watch flood risk change)

All the real logic lives in services/blockage_detector.py.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify, request

from models import Drain

drain_bp = Blueprint("drain", __name__)


def _drain_with_latest_reading(drain: Drain) -> dict:
    latest = drain.readings.first()
    return {
        **drain.to_dict(),
        "latest_reading": latest.to_dict() if latest else None,
    }


@drain_bp.route("/drains", methods=["GET"])
def list_drains():
    zone_id = request.args.get("zone_id", type=int)
    query = Drain.query
    if zone_id is not None:
        query = query.filter_by(zone_id=zone_id)
    drains = query.order_by(Drain.drain_code.asc()).all()

    return jsonify({
        "data": [_drain_with_latest_reading(d) for d in drains],
        "meta": {"source": "database", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200


@drain_bp.route("/drains/<int:drain_id>", methods=["GET"])
def get_drain(drain_id):
    drain = Drain.query.get(drain_id)
    if drain is None:
        return jsonify({"data": None, "error": f"No drain with id {drain_id}"}), 404

    history_limit = request.args.get("history_limit", default=20, type=int)
    recent_readings = drain.readings.limit(min(history_limit, 100)).all()

    return jsonify({
        "data": {
            **drain.to_dict(),
            "latest_reading": recent_readings[0].to_dict() if recent_readings else None,
            "reading_history": [r.to_dict() for r in recent_readings],
        },
        "meta": {"source": "database", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200


@drain_bp.route("/drains/<int:drain_id>/simulate-blockage", methods=["POST"])
def simulate_drain_blockage(drain_id):
    drain = Drain.query.get(drain_id)
    if drain is None:
        return jsonify({"data": None, "error": f"No drain with id {drain_id}"}), 404

    body = request.get_json(silent=True) or {}
    blockage_percent = body.get("blockage_percent")
    if blockage_percent is None:
        return jsonify({
            "data": None,
            "error": "Request body must include numeric 'blockage_percent' (0-100).",
        }), 400
    try:
        blockage_percent = float(blockage_percent)
    except (TypeError, ValueError):
        return jsonify({"data": None, "error": "'blockage_percent' must be a number."}), 400

    from services.blockage_detector import simulate_blockage_for_drain
    result = simulate_blockage_for_drain(drain, blockage_percent)

    return jsonify({
        "data": result,
        "meta": {"source": "simulated", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200

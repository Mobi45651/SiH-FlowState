"""
routes/alert_routes.py
--------------------------
GET /api/alerts                    -> READ ONLY: returns active/resolved alerts
GET /api/alerts?zone_id=<id>       -> READ ONLY, filtered to one zone
GET /api/alerts?status=resolved    -> view resolved alerts instead
POST /api/alerts/refresh           -> explicit write operation that regenerates alerts

GET never regenerates predictions or alerts. This separation prevents the
dashboard/location dropdown from creating concurrent SQLite write transactions.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify, request

from models import Alert, Zone
from services.alert_service import generate_alerts_for_all_zones, generate_alerts_for_zone

alert_bp = Blueprint("alert", __name__)


@alert_bp.route("/alerts", methods=["GET"])
def list_alerts():
    zone_id = request.args.get("zone_id", type=int)
    status = request.args.get("status", default="active")

    query = Alert.query
    if zone_id is not None:
        if Zone.query.get(zone_id) is None:
            return jsonify({"data": None, "error": f"No zone with id {zone_id}"}), 404
        query = query.filter_by(zone_id=zone_id)
    if status in ("active", "resolved"):
        query = query.filter_by(status=status)

    alerts = query.order_by(Alert.created_at.desc()).all()
    return jsonify({
        "data": [a.to_dict() for a in alerts],
        "meta": {"source": "database", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200


@alert_bp.route("/alerts/refresh", methods=["POST"])
def refresh_alerts():
    zone_id = request.args.get("zone_id", type=int)
    if zone_id is not None:
        zone = Zone.query.get(zone_id)
        if zone is None:
            return jsonify({"data": None, "error": f"No zone with id {zone_id}"}), 404
        created = generate_alerts_for_zone(zone)
    else:
        created = generate_alerts_for_all_zones()
    return jsonify({"data": [a.to_dict() for a in created], "meta": {"source": "refresh"}}), 200


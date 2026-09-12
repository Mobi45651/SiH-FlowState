"""
routes/zone_routes.py
------------------------
Simple read endpoints over the zones table. Added in Phase 5 alongside the
nowcast API because a zone_id is required to query /api/nowcast and
/api/flood-risk -- this is how the frontend (and you, testing by hand)
discovers valid zone IDs/codes/names in the first place.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify

from models import Zone

zone_bp = Blueprint("zone", __name__)


@zone_bp.route("/zones", methods=["GET"])
def list_zones():
    zones = Zone.query.order_by(Zone.zone_code.asc()).all()
    return jsonify({
        "data": [z.to_dict() for z in zones],
        "meta": {"source": "database", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200


@zone_bp.route("/zones/<int:zone_id>", methods=["GET"])
def get_zone(zone_id):
    zone = Zone.query.get(zone_id)
    if zone is None:
        return jsonify({"data": None, "error": f"No zone with id {zone_id}"}), 404
    return jsonify({
        "data": zone.to_dict(),
        "meta": {"source": "database", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200

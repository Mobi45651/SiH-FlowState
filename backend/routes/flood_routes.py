"""
routes/flood_routes.py
--------------------------
GET /api/flood-risk              -> current risk snapshot, every zone
GET /api/flood-risk/<zone_id>    -> current risk snapshot, one zone

"Current" = the first ("NOW") step of that zone's nowcast. This
deliberately reuses services/nowcast_engine.py rather than a separate
code path, so /api/flood-risk and /api/nowcast can never disagree with
each other about the present moment.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify

from models import Zone
from services.nowcast_engine import get_cached_zone_nowcast, get_cached_all_zone_nowcasts

flood_bp = Blueprint("flood", __name__)


def _current_snapshot(nowcast_result: dict) -> dict:
    now_step = nowcast_result["forecast"][0]
    return {
        "zone_id": nowcast_result["zone_id"],
        "zone_code": nowcast_result["zone_code"],
        "zone_name": nowcast_result["zone_name"],
        **now_step,
    }


@flood_bp.route("/flood-risk", methods=["GET"])
def get_flood_risk_all():
    results = get_cached_all_zone_nowcasts()
    snapshots = [_current_snapshot(r) for r in results]
    return jsonify({
        "data": snapshots,
        "meta": {"source": "computed", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200


@flood_bp.route("/flood-risk/<int:zone_id>", methods=["GET"])
def get_flood_risk_zone(zone_id):
    zone = Zone.query.get(zone_id)
    if zone is None:
        return jsonify({"data": None, "error": f"No zone with id {zone_id}"}), 404

    result = get_cached_zone_nowcast(zone)
    return jsonify({
        "data": _current_snapshot(result),
        "meta": {"source": "computed", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200

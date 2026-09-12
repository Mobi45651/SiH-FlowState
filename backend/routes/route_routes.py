"""
routes/route_routes.py
--------------------------
GET /api/routes                 -> the seeded demo road-segment graph
                                    (optionally filtered by zone_id)
POST /api/routes/safe           -> body {"from_lat", "from_lng", "to_lat", "to_lng"}
                                    (optionally "from_label"/"to_label" for
                                    display only) -> normal vs flood-safe route

All the real logic lives in services/routing_service.py.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify, request

from models import RouteSegment
from services.routing_service import calculate_safe_route

route_bp = Blueprint("route", __name__)


@route_bp.route("/routes", methods=["GET"])
def list_route_segments():
    zone_id = request.args.get("zone_id", type=int)
    query = RouteSegment.query
    if zone_id is not None:
        query = query.filter_by(zone_id=zone_id)
    segments = query.order_by(RouteSegment.road_name.asc()).all()

    return jsonify({
        "data": [s.to_dict() for s in segments],
        "meta": {"source": "database", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200


@route_bp.route("/routes/geojson", methods=["GET"])
def route_geojson_endpoint():
    from services.routing_service import route_geojson
    offset = request.args.get("offset_minutes", default=0, type=int)
    offset = max(0, min(180, offset))
    return jsonify({"data": route_geojson(offset), "meta": {"source": "computed", "street_level": True, "offset_minutes": offset}}), 200


@route_bp.route("/routes/safe", methods=["POST"])
def get_safe_route():
    body = request.get_json(silent=True) or {}

    required = ["from_lat", "from_lng", "to_lat", "to_lng"]
    missing = [k for k in required if k not in body]
    if missing:
        return jsonify({
            "data": None,
            "error": f"Request body is missing required field(s): {missing}. "
                     f"Expected numeric from_lat, from_lng, to_lat, to_lng.",
        }), 400

    try:
        from_lat, from_lng = float(body["from_lat"]), float(body["from_lng"])
        to_lat, to_lng = float(body["to_lat"]), float(body["to_lng"])
    except (TypeError, ValueError):
        return jsonify({"data": None, "error": "from_lat/from_lng/to_lat/to_lng must be numbers."}), 400

    result = calculate_safe_route(
        from_lat, from_lng, to_lat, to_lng,
        from_label=body.get("from_label"), to_label=body.get("to_label"),
    )

    return jsonify({
        "data": result,
        "meta": {"source": "computed", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200

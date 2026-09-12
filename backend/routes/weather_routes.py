"""
routes/weather_routes.py
---------------------------
GET /api/weather?zone_id=<id>            -> live/cached weather for that zone
GET /api/weather?zone_id=<id>&refresh=1  -> bypass cache, force a fresh Open-Meteo call
GET /api/weather?zone_id=<id>&ingest=1   -> also runs the rainfall pipeline
                                             for this zone (stores it in the DB)

The response includes requested and provider coordinates, current timestamp,
current temperature/apparent temperature, grid-cell selection, and model so
weather discrepancies can be audited instead of guessed.

Kept thin on purpose: all the real logic lives in
services/weather_service.py and services/rainfall_pipeline.py.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify, request

from models import Zone
from services.weather_service import fetch_weather_for_zone, get_weather_for_coordinates
from services.rainfall_pipeline import ingest_zone_rainfall

weather_bp = Blueprint("weather", __name__)


@weather_bp.route("/weather", methods=["GET"])
def get_weather():
    zone_id = request.args.get("zone_id", type=int)
    if zone_id is None:
        return jsonify({
            "data": None,
            "error": "zone_id query parameter is required, e.g. /api/weather?zone_id=1",
        }), 400

    zone = Zone.query.get(zone_id)
    if zone is None:
        return jsonify({"data": None, "error": f"No zone with id {zone_id}"}), 404

    force_refresh = request.args.get("refresh", "0") in ("1", "true", "True")
    should_ingest = request.args.get("ingest", "0") in ("1", "true", "True")

    weather_data = fetch_weather_for_zone(zone, allow_demo_fallback=True, force_refresh=force_refresh)

    ingest_summary = None
    if should_ingest:
        # Re-fetches internally via the pipeline; cache makes this cheap
        # unless force_refresh was also set.
        ingest_summary = ingest_zone_rainfall(zone, allow_demo_fallback=True, force_refresh=force_refresh)

    return jsonify({
        "data": {
            "zone": zone.to_dict(),
            "weather": weather_data,
            "ingest_summary": ingest_summary,
        },
        "meta": {
            "source": weather_data["source"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }), 200

@weather_bp.route("/weather/location", methods=["GET"])
def get_weather_for_location():
    """GET /api/weather/location?lat=<lat>&lng=<lng> -> live weather at a browser GPS location.

    This endpoint is intentionally independent of the seeded Zone table so the
    dashboard can show the user's actual location instead of defaulting to the
    seeded Gurugram monitoring zones.
    """
    try:
        latitude = float(request.args.get("lat"))
        longitude = float(request.args.get("lng"))
    except (TypeError, ValueError):
        return jsonify({"data": None, "error": "lat and lng must be valid numbers"}), 400

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return jsonify({"data": None, "error": "lat/lng are outside valid coordinate ranges"}), 400

    force_refresh = request.args.get("refresh", "1") in ("1", "true", "True")
    try:
        weather_data = get_weather_for_coordinates(latitude, longitude, force_refresh=force_refresh)
    except Exception as exc:
        return jsonify({"data": None, "error": str(exc)}), 502

    return jsonify({
        "data": {
            "location": {"latitude": latitude, "longitude": longitude},
            "weather": weather_data,
        },
        "meta": {
            "source": weather_data["source"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }), 200

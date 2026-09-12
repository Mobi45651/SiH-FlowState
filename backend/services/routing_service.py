"""
services/routing_service.py
------------------------------
Orchestrates the Safe Route Planner:
1. (Optional) fetch a real base distance/time from OpenRouteService if
   ROUTING_API_KEY is configured -- isolated to _fetch_real_route() below,
   exactly as the spec requires ("clearly isolate it in a service module
   and store the API key in .env"). Falls back to the demo straight-line
   estimate on any failure, and ALWAYS labels which one was actually used.
2. Figures out which zones the route passes near (by sampling points along
   the path and finding each one's nearest zone), looks up each zone's
   CURRENT flood risk (reusing services/nowcast_engine.py so this never
   disagrees with /api/nowcast), and collects that zone's flagged
   high-risk road segments as "avoided" in the safe-route alternative.
3. Combines both into the normal-vs-safe comparison the API returns.

Connects to:
- flood_engine/routing.py    -> the actual distance/time/detour math
- services/nowcast_engine.py -> current risk per zone along the path
- models/zone.py, models/route_segment.py -> what gets queried
- routes/route_routes.py     -> exposes this over HTTP
"""

import logging

import requests
from flask import current_app

from models import Zone, RouteSegment
from services.nowcast_engine import build_zone_nowcast
from flood_engine.routing import (
    haversine_distance_km,
    estimate_road_distance_km,
    estimate_travel_time_minutes,
    worst_risk,
    compute_safe_route,
    build_route_explanation,
)

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 8
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"


class RoutingServiceError(Exception):
    """Raised when the real routing API call or response parsing fails."""


def _fetch_real_route(from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> dict:
    """Calls OpenRouteService for a real base distance/time. Isolated here
    so this is the ONLY function that talks to an external routing
    provider. Raises RoutingServiceError on any failure -- callers decide
    whether to fall back to the demo estimate."""
    api_key = current_app.config.get("ROUTING_API_KEY")
    if not api_key:
        raise RoutingServiceError("No ROUTING_API_KEY configured")

    params = {
        "api_key": api_key,
        "start": f"{from_lng},{from_lat}",  # ORS wants lng,lat order
        "end": f"{to_lng},{to_lat}",
    }
    try:
        response = requests.get(ORS_DIRECTIONS_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise RoutingServiceError(f"Routing API request failed: {exc}") from exc

    try:
        payload = response.json()
        summary = payload["features"][0]["properties"]["summary"]
        distance_km = round(summary["distance"] / 1000, 2)
        duration_min = round(summary["duration"] / 60, 1)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RoutingServiceError(f"Unexpected routing API response shape: {exc}") from exc

    return {"distance_km": distance_km, "duration_minutes": duration_min}


def _get_base_route(from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> dict:
    """Returns {distance_km, duration_minutes, source}. Tries the real API
    first (if configured), falls back to the demo straight-line estimate
    on any failure -- and the "source" field always tells you honestly
    which one produced the numbers you're looking at."""
    try:
        real = _fetch_real_route(from_lat, from_lng, to_lat, to_lng)
        return {**real, "source": "openrouteservice"}
    except RoutingServiceError as exc:
        logger.info("Falling back to demo route estimate: %s", exc)
        straight_km = haversine_distance_km(from_lat, from_lng, to_lat, to_lng)
        distance_km = estimate_road_distance_km(straight_km)
        duration_min = estimate_travel_time_minutes(distance_km)
        return {"distance_km": distance_km, "duration_minutes": duration_min, "source": "demo_estimate"}


def _find_nearest_zone(lat: float, lng: float, zones: list) -> Zone | None:
    if not zones:
        return None
    return min(zones, key=lambda z: haversine_distance_km(lat, lng, z.latitude, z.longitude))


def _sample_zones_along_path(from_lat, from_lng, to_lat, to_lng, num_samples: int = 5) -> list:
    """Linearly interpolates points along the straight-line path and finds
    each one's nearest zone -- a coarse proxy for "which zones does this
    route pass through/near", since there's no real routable road graph
    to trace (see flood_engine/routing.py docstring)."""
    all_zones = Zone.query.all()
    if not all_zones:
        return []

    seen_ids = set()
    zones_along_path = []
    for i in range(num_samples):
        fraction = i / (num_samples - 1) if num_samples > 1 else 0
        sample_lat = from_lat + (to_lat - from_lat) * fraction
        sample_lng = from_lng + (to_lng - from_lng) * fraction
        nearest = _find_nearest_zone(sample_lat, sample_lng, all_zones)
        if nearest is not None and nearest.id not in seen_ids:
            seen_ids.add(nearest.id)
            zones_along_path.append(nearest)
    return zones_along_path


def get_road_segments_geojson(offset_minutes: int = 0) -> dict:
    """Returns every seeded road segment as a GeoJSON FeatureCollection,
    with each segment's risk_category computed LIVE from its own zone's
    nowcast at the given time offset (0/30/60/90/120/150/180 minutes) --
    NOT the static value written at seed time.

    HONESTY NOTE: "street-level" here means each road inherits its parent
    zone's predicted risk at that forecast step -- it is NOT an
    independent per-street hydrology model. Real street-by-street
    prediction would need per-street elevation and drainage data this
    prototype doesn't have (see flood_engine/routing.py's module
    docstring for the same limitation applied to routing).

    Connects to:
    - models/route_segment.py    -> the road geometry or this operates over
    - services/nowcast_engine.py -> supplies each zone's time-varying risk
    - routes/route_routes.py     -> exposes this over GET /api/routes/geojson
    """
    segments = RouteSegment.query.all()
    if not segments:
        return {"type": "FeatureCollection", "features": []}

    zone_ids = {s.zone_id for s in segments}
    zones_by_id = {z.id: z for z in Zone.query.filter(Zone.id.in_(zone_ids)).all()}

    # One nowcast per zone (not per segment) -- several segments usually
    # share a zone, no need to recompute its forecast for each of them.
    risk_by_zone = {}
    for zone_id, zone in zones_by_id.items():
        forecast = build_zone_nowcast(zone)["forecast"]
        closest_step = min(forecast, key=lambda step: abs(step["offset_minutes"] - offset_minutes))
        risk_by_zone[zone_id] = closest_step["risk_category"]

    features = []
    for s in segments:
        risk = risk_by_zone.get(s.zone_id, s.risk_category)
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[s.start_lng, s.start_lat], [s.end_lng, s.end_lat]],
            },
            "properties": {
                "id": s.id,
                "road_name": s.road_name,
                "zone_id": s.zone_id,
                "distance_km": s.distance_km,
                "is_flood_prone": s.is_flood_prone,
                "risk_category": risk,
            },
        })
    return {"type": "FeatureCollection", "features": features}


def calculate_safe_route(
    from_lat: float, from_lng: float, to_lat: float, to_lng: float,
    from_label: str | None = None, to_label: str | None = None,
) -> dict:
    base = _get_base_route(from_lat, from_lng, to_lat, to_lng)
    normal_distance_km = base["distance_km"]
    normal_duration_min = base["duration_minutes"]

    zones_along_path = _sample_zones_along_path(from_lat, from_lng, to_lat, to_lng)
    zone_risks = {z.id: build_zone_nowcast(z)["forecast"][0]["risk_category"] for z in zones_along_path}
    normal_risk = worst_risk(list(zone_risks.values()))

    high_risk_zone_ids = [zid for zid, risk in zone_risks.items() if risk in ("HIGH", "SEVERE")]

    # "Avoided" segments: any segment seeded as flood-prone in a zone the
    # route passes through, PLUS segments in any zone whose LIVE current
    # risk is HIGH/SEVERE even if its seeded segment data said otherwise --
    # keeps the avoided-segment list honest against the live nowcast, not
    # just the static seed data.
    zone_ids_along_path = [z.id for z in zones_along_path]
    avoided_segments = []
    if zone_ids_along_path:
        candidates = RouteSegment.query.filter(RouteSegment.zone_id.in_(zone_ids_along_path)).all()
        avoided_segments = [
            s for s in candidates
            if s.is_flood_prone or s.zone_id in high_risk_zone_ids
        ]

    num_avoided = len(avoided_segments)
    safe_distance_km, safe_duration_min = compute_safe_route(normal_distance_km, normal_duration_min, num_avoided)
    # The safe route still passes through any zone that WASN'T high-risk
    # (that's the whole point -- only HIGH/SEVERE zones get detoured
    # around). Its risk label must reflect whatever's left, not just
    # assume "avoided something" means "now entirely LOW risk".
    remaining_zone_risks = [risk for zid, risk in zone_risks.items() if zid not in high_risk_zone_ids]
    safe_risk = worst_risk(remaining_zone_risks) if num_avoided > 0 else normal_risk
    explanation = build_route_explanation(normal_distance_km, safe_distance_km, num_avoided)

    return {
        "from": {"latitude": from_lat, "longitude": from_lng, "label": from_label},
        "to": {"latitude": to_lat, "longitude": to_lng, "label": to_label},
        "normal_route": {
            "distance_km": normal_distance_km,
            "duration_minutes": normal_duration_min,
            "risk": normal_risk,
            "source": base["source"],
        },
        "safe_route": {
            "distance_km": safe_distance_km,
            "duration_minutes": safe_duration_min,
            "risk": safe_risk,
            "source": "demo_detour_estimate" if num_avoided > 0 else base["source"],
        },
        "avoided_segments": [s.to_dict() for s in avoided_segments],
        "zones_considered": [z.zone_code for z in zones_along_path],
        "explanation": explanation,
    }
